"""
modules.audio_analyze

Full audio analysis modul (Faza 1, 2 i 3) za Z-Music Organizer, jazz-fokusiran.

- Faza 1: CLAP audio embedding (global + segmentirani)
- Faza 2: Librosa spectral feature-i, tempo, beat density, chord_complexity...
- Faza 3: Zero-shot žanr, mood i instrumenti koristeći CLAP + tekstualne promptove

Ključne stvari:
- koristi config.py (BASE_MUSIC_PATH, ANALYSIS)
- piše .analysis.json uz svaku audio datoteku
- ima --info argument koji čita JSON i prikazuje tablicu najbitnijih feature-a
- utišava Roberta / Transformers warninge, laion_clap log spam i "Loaded" ispis
- pokušava riješiti SSL CERTIFICATE_VERIFY_FAILED preko certifi
- nakon svake analize ispisuje sažetak (trajanje obrade, putanja JSON-a, žanr, mood, instrumenti, osnovni feature-i)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import tempfile
import warnings
import time
import contextlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# -------------------------------------------------------------------------
# Warning / logging mute
# -------------------------------------------------------------------------

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)
logging.getLogger("numba").setLevel(logging.ERROR)
logging.getLogger("librosa").setLevel(logging.ERROR)

# Dodatno: stišaj Transformers preko env var
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

# -------------------------------------------------------------------------
# Config import
# -------------------------------------------------------------------------

try:
    from config import BASE_MUSIC_PATH, ANALYSIS  # type: ignore
except Exception:  # pragma: no cover - fallback ako config nije kompletan
    BASE_MUSIC_PATH = Path(".")
    @dataclass(frozen=True)
    class _FallbackAnalysis:
        analysis_suffix: str = ".analysis.json"
        supported_exts: tuple[str, ...] = (".flac", ".wav", ".mp3", ".m4a", ".ogg")
        clap_model_name: str = "laion/clap-htsat-unfused"
        clap_device: str = "auto"
        segment_seconds: int = 15
        max_segments: int = 20
    ANALYSIS = _FallbackAnalysis()

# -------------------------------------------------------------------------
# Third-party libs
# -------------------------------------------------------------------------

import numpy as np
import certifi
import librosa
import soundfile as sf

# Pokušaj popraviti SSL na macOS / custom Pythonevima
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

try:
    import laion_clap  # type: ignore
except ImportError as e:  # pragma: no cover
    print("Greška: paket 'laion-clap' nije instaliran. Instaliraj ga sa:", file=sys.stderr)
    print("    pip install laion-clap librosa soundfile", file=sys.stderr)
    raise SystemExit(1) from e

# Mute Transformers / CLAP log spam (Roberta weights, training hints, progress barovi)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("laion_clap").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

# -------------------------------------------------------------------------
# CLAP model cache
# -------------------------------------------------------------------------

_CLAP_MODEL = None
_CLAP_DEVICE = None


def _resolve_device(cfg_device: str) -> str:
    """Vrati 'cuda' ako je moguće, inače 'cpu'."""
    import torch

    if cfg_device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return cfg_device


def get_clap_model():
    """Lazy-load CLAP model i vrati ga (cached).

    load_ckpt je ušutkan redirectom stdout/stderr kako "Loaded ..." i slične
    poruke ne bi zatrpavale tvoj terminal.
    """
    global _CLAP_MODEL, _CLAP_DEVICE
    if _CLAP_MODEL is not None:
        return _CLAP_MODEL

    device = _resolve_device(getattr(ANALYSIS, "clap_device", "auto"))
    _CLAP_DEVICE = device

    model = laion_clap.CLAP_Module(enable_fusion=False, device=device)
    # load_ckpt() automatski povlači default checkpoint ako nije lokalno.
    # Ušutkaj sav ispis koji CLAP radi na stdout/stderr.
    with open(os.devnull, "w") as devnull,              contextlib.redirect_stdout(devnull),              contextlib.redirect_stderr(devnull):
        model.load_ckpt()

    _CLAP_MODEL = model
    return _CLAP_MODEL


# -------------------------------------------------------------------------
# Dataclasses za JSON
# -------------------------------------------------------------------------

@dataclass
class EmbeddingInfo:
    global_mean: List[float]
    segment_vectors: List[List[float]]
    segment_seconds: int
    segments_used: int


@dataclass
class FeatureInfo:
    duration: float
    sample_rate: int
    tempo: float
    beat_density: float
    rms: float
    spectral_centroid: float
    spectral_bandwidth: float
    spectral_rolloff: float
    spectral_flatness: float
    spectral_contrast: List[float]
    zero_crossing_rate: float
    chord_complexity: float
    key: str
    energy: float


@dataclass
class GenreInfo:
    primary: str
    alt_1: Optional[str]
    alt_2: Optional[str]
    confidence: float


@dataclass
class MoodInfo:
    valence: float
    arousal: float
    tag: str


@dataclass
class InstrumentInfo:
    lead_instrument: Optional[str]
    bass_type: Optional[str]
    drums_pattern: Optional[str]
    raw_scores: Dict[str, float]


@dataclass
class AnalysisJSON:
    version: str
    file: str
    rel_path_from_root: str
    embedding: EmbeddingInfo
    features: FeatureInfo
    genre: GenreInfo
    mood: MoodInfo
    instruments: InstrumentInfo


# -------------------------------------------------------------------------
# Helperi: audio / feature / embedding
# -------------------------------------------------------------------------

def _load_audio(path: Path, sr: Optional[int] = None) -> Tuple[np.ndarray, int]:
    y, sr = librosa.load(path, sr=sr, mono=True)
    return y, sr


def _estimate_key(chroma: np.ndarray) -> str:
    # Vrlo gruba procjena tonaliteta: globalni maksimum u chroma.
    pitch_energy = chroma.mean(axis=1)
    idx = int(np.argmax(pitch_energy))
    pitch_names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    key = pitch_names[idx]
    # major/minor heuristika via brightness
    brightness = pitch_energy[[0, 2, 4, 5, 7, 9, 11]].sum() - pitch_energy[[1, 3, 6, 8, 10]].sum()
    mode = "maj" if brightness >= 0 else "min"
    return f"{key}{mode}"


def compute_features(path: Path) -> FeatureInfo:
    y, sr = _load_audio(path, sr=None)
    duration = float(librosa.get_duration(y=y, sr=sr))

    # Tempo & beat density
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_density = float(len(beat_frames) / duration) if duration > 0 else 0.0

    # Spectral features
    S_cent = librosa.feature.spectral_centroid(y=y, sr=sr)
    S_bw = librosa.feature.spectral_bandwidth(y=y, sr=sr)
    S_roll = librosa.feature.spectral_rolloff(y=y, sr=sr)
    S_flat = librosa.feature.spectral_flatness(y=y)
    S_contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    ZCR = librosa.feature.zero_crossing_rate(y)
    RMS = librosa.feature.rms(y=y)

    centroid = float(S_cent.mean())
    bandwidth = float(S_bw.mean())
    rolloff = float(S_roll.mean())
    flatness = float(S_flat.mean())
    contrast = S_contrast.mean(axis=1).astype(float).tolist()
    zcr = float(ZCR.mean())
    rms = float(RMS.mean())

    # Chroma & chord_complexity
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)
    active_notes = (chroma_mean > 0.1 * chroma_mean.max()).sum()
    chord_complexity = float(active_notes / 12.0)

    key = _estimate_key(chroma)

    # Energy normalizirana u rasponu 0-1
    energy = float(np.clip(rms * 10, 0.0, 1.0))

    return FeatureInfo(
        duration=duration,
        sample_rate=int(sr),
        tempo=float(tempo),
        beat_density=beat_density,
        rms=rms,
        spectral_centroid=centroid,
        spectral_bandwidth=bandwidth,
        spectral_rolloff=rolloff,
        spectral_flatness=flatness,
        spectral_contrast=contrast,
        zero_crossing_rate=zcr,
        chord_complexity=chord_complexity,
        key=key,
        energy=energy,
    )


def compute_clap_embeddings(path: Path) -> EmbeddingInfo:
    model = get_clap_model()

    # Prvo globalni embedding (cijeli file)
    audio_paths = [str(path)]
    global_emb = model.get_audio_embedding_from_filelist(x=audio_paths, use_tensor=False)
    global_vec = np.asarray(global_emb, dtype=np.float32)[0]
    # L2 normiranje
    norm = np.linalg.norm(global_vec) + 1e-8
    global_vec = global_vec / norm

    # Segmentirani embeddingi
    seg_sec = getattr(ANALYSIS, "segment_seconds", 15)
    max_segs = getattr(ANALYSIS, "max_segments", 20)

    y, sr = _load_audio(path, sr=48000)
    total_samples = y.shape[0]
    seg_samples = int(seg_sec * sr)
    if seg_samples <= 0 or total_samples <= seg_samples:
        segment_vectors = [global_vec.tolist()]
        return EmbeddingInfo(
            global_mean=global_vec.tolist(),
            segment_vectors=segment_vectors,
            segment_seconds=seg_sec,
            segments_used=len(segment_vectors),
        )

    segments = []
    for start in range(0, total_samples, seg_samples):
        end = start + seg_samples
        if end - start < seg_samples * 0.4:  # preskoči prekratke
            break
        segments.append(y[start:end])

    if len(segments) > max_segs:
        # Uniformno sample-aj segmente
        idxs = np.linspace(0, len(segments) - 1, num=max_segs, dtype=int)
        segments = [segments[i] for i in idxs]

    tmp_wavs: List[Path] = []
    try:
        for i, seg in enumerate(segments):
            tmp_fd, tmp_name = tempfile.mkstemp(suffix=".wav")
            os.close(tmp_fd)
            tmp_path = Path(tmp_name)
            sf.write(tmp_path, seg, sr)
            tmp_wavs.append(tmp_path)

        seg_emb = model.get_audio_embedding_from_filelist(
            x=[str(p) for p in tmp_wavs],
            use_tensor=False,
        )
        seg_arr = np.asarray(seg_emb, dtype=np.float32)
        # L2 normiranje svakog segmenta
        seg_norms = np.linalg.norm(seg_arr, axis=1, keepdims=True) + 1e-8
        seg_arr = seg_arr / seg_norms
    finally:
        for p in tmp_wavs:
            try:
                p.unlink()
            except FileNotFoundError:
                pass

    # Globalni = prosjek segmenata
    global_from_segments = seg_arr.mean(axis=0)
    gnorm = np.linalg.norm(global_from_segments) + 1e-8
    global_from_segments = global_from_segments / gnorm

    return EmbeddingInfo(
        global_mean=global_from_segments.astype(float).tolist(),
        segment_vectors=seg_arr.astype(float).tolist(),
        segment_seconds=seg_sec,
        segments_used=int(seg_arr.shape[0]),
    )


# -------------------------------------------------------------------------
# Faza 3 – Zero-shot žanr, mood, instrumenti (jazz fokus)
# -------------------------------------------------------------------------

GENRE_LABELS = [
    "modern jazz",
    "bebop",
    "hard bop",
    "cool jazz",
    "modal jazz",
    "free jazz",
    "jazz ballad",
    "latin jazz",
    "bossa nova",
    "samba jazz",
    "soul jazz",
    "funk jazz",
    "jazz fusion",
    "big band swing",
    "gypsy jazz",
    "smooth jazz",
    "solo piano jazz",
    "jazz piano trio",
    "organ jazz trio",
    "lofi jazz / chillhop",
]

MOOD_AXES = {
    "valence_pos": "very happy, bright and uplifting jazz music",
    "valence_neg": "very sad, dark and melancholic jazz ballad",
    "arousal_high": "very energetic, intense and driving jazz or fusion track",
    "arousal_low": "very calm, soft and relaxing jazz or lounge track",
}

INSTRUMENT_PROMPTS = {
    "saxophone": "a jazz quartet with saxophone as the clear lead solo instrument",
    "trumpet": "a jazz group where trumpet is the main solo instrument",
    "piano": "a modern jazz track where acoustic piano leads the melody",
    "electric_guitar": "a jazz or fusion track with electric guitar as the lead instrument",
    "acoustic_guitar": "a gypsy jazz or acoustic jazz track with guitar playing the main melody",
    "vocal": "a vocal jazz ballad with a prominent human singer in front of the band",
    "upright_bass": "a classic jazz recording with walking upright acoustic bass",
    "electric_bass": "a jazz fusion or funk-jazz track with electric bass guitar",
    "drums_swing": "a jazz drum kit playing a ride-cymbal swing groove with walking bass",
    "drums_straight": "a straight 8th jazz, pop-jazz or funk groove on drums without swing feel",
    "drums_shuffle": "a jazz or blues shuffle groove on the drum kit",
}


def _clap_text_similarity(global_vec: np.ndarray, texts: Sequence[str]) -> np.ndarray:
    model = get_clap_model()
    text_emb = model.get_text_embedding(list(texts))
    text_arr = np.asarray(text_emb, dtype=np.float32)
    # L2 norm
    t_norm = np.linalg.norm(text_arr, axis=1, keepdims=True) + 1e-8
    text_arr = text_arr / t_norm
    g = global_vec.reshape(1, -1)
    sims = (g @ text_arr.T)[0]
    return sims


def infer_genre(global_vec: np.ndarray) -> GenreInfo:
    prompts = [f"a {g} music track" for g in GENRE_LABELS]
    sims = _clap_text_similarity(global_vec, prompts)
    # Pretvori u pseudo-probabilities
    exp = np.exp(sims - sims.max())
    probs = exp / exp.sum()
    idx_sorted = np.argsort(-probs)
    primary_idx = int(idx_sorted[0])
    alt1_idx = int(idx_sorted[1]) if len(idx_sorted) > 1 else None
    alt2_idx = int(idx_sorted[2]) if len(idx_sorted) > 2 else None

    primary = GENRE_LABELS[primary_idx]
    alt1 = GENRE_LABELS[alt1_idx] if alt1_idx is not None else None
    alt2 = GENRE_LABELS[alt2_idx] if alt2_idx is not None else None

    confidence = float(probs[primary_idx])
    return GenreInfo(primary=primary, alt_1=alt1, alt_2=alt2, confidence=confidence)


def infer_mood(global_vec: np.ndarray) -> MoodInfo:
    prompts = list(MOOD_AXES.values())
    sims = _clap_text_similarity(global_vec, prompts)
    valence = float((sims[0] - sims[1]) * 0.5 + 0.5)  # map na [0,1]
    arousal = float((sims[2] - sims[3]) * 0.5 + 0.5)

    # Tag generiraj na temelju kvadranta
    if valence >= 0.5 and arousal >= 0.5:
        tag = "energetic / happy"
    elif valence >= 0.5 and arousal < 0.5:
        tag = "calm / positive"
    elif valence < 0.5 and arousal >= 0.5:
        tag = "tense / dark"
    else:
        tag = "calm / melancholic"

    return MoodInfo(valence=valence, arousal=arousal, tag=tag)


def infer_instruments(global_vec: np.ndarray) -> InstrumentInfo:
    prompts = list(INSTRUMENT_PROMPTS.values())
    keys = list(INSTRUMENT_PROMPTS.keys())
    sims = _clap_text_similarity(global_vec, prompts)

    # Normaliziraj na [0,1]
    sims_norm = (sims - sims.min()) / (sims.max() - sims.min() + 1e-8)
    raw_scores = {k: float(v) for k, v in zip(keys, sims_norm)}

    # Lead instrument = max od specifičnih lead instrumenata
    lead_candidates = ["saxophone", "trumpet", "piano", "electric_guitar", "acoustic_guitar", "vocal"]
    lead_inst = max(lead_candidates, key=lambda k: raw_scores.get(k, 0.0))
    lead_inst_score = raw_scores.get(lead_inst, 0.0)
    lead_inst_final = lead_inst if lead_inst_score > 0.3 else None

    # Bass type
    bass_candidates = ["upright_bass", "electric_bass"]
    bass_type = max(bass_candidates, key=lambda k: raw_scores.get(k, 0.0))
    bass_score = raw_scores.get(bass_type, 0.0)
    bass_final = bass_type if bass_score > 0.3 else None

    # Drums pattern
    drums_candidates = ["drums_swing", "drums_straight", "drums_shuffle"]
    drums_type = max(drums_candidates, key=lambda k: raw_scores.get(k, 0.0))
    drums_score = raw_scores.get(drums_type, 0.0)
    drums_final = drums_type if drums_score > 0.3 else None

    return InstrumentInfo(
        lead_instrument=lead_inst_final,
        bass_type=bass_final,
        drums_pattern=drums_final,
        raw_scores=raw_scores,
    )


# -------------------------------------------------------------------------
# Main analiza jedne datoteke
# -------------------------------------------------------------------------

def analyze_file(audio_path: Path, root: Path) -> AnalysisJSON:
    audio_path = audio_path.resolve()
    try:
        rel_path = audio_path.relative_to(root.resolve())
    except Exception:
        rel_path = audio_path.name

    feats = compute_features(audio_path)
    emb = compute_clap_embeddings(audio_path)

    global_vec = np.asarray(emb.global_mean, dtype=np.float32)
    genre = infer_genre(global_vec)
    mood = infer_mood(global_vec)
    instruments = infer_instruments(global_vec)

    return AnalysisJSON(
        version="1.0.0",
        file=audio_path.name,
        rel_path_from_root=str(rel_path),
        embedding=emb,
        features=feats,
        genre=genre,
        mood=mood,
        instruments=instruments,
    )


def write_analysis_json(analysis: AnalysisJSON, audio_path: Path) -> Path:
    """Zapiši analysis JSON kao SKRIVENI file uz audio.

    Konvencija (usklađena s .final.json i .spotify.json):

        audio:  /.../351 Lake Shore Drive - Chill Bill.mp3
        json:   /.../.351 Lake Shore Drive - Chill Bill.analysis.json
    """
    suffix = getattr(ANALYSIS, "analysis_suffix", ".analysis.json")

    # Osnovno ime bez ekstenzije (.mp3, .flac...)
    base_name = audio_path.stem  # npr. "351 Lake Shore Drive - Chill Bill"

    # Skriveni naziv datoteke: .<base_name>.analysis.json
    hidden_name = f".{base_name}{suffix}"
    out_path = audio_path.with_name(hidden_name)

    payload = asdict(analysis)

    def _default(o):
        import numpy as _np
        if isinstance(o, (_np.floating,)):
            return float(o)
        if isinstance(o, (_np.integer,)):
            return int(o)
        return str(o)

    out_path.write_text(json.dumps(payload, default=_default, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path



# -------------------------------------------------------------------------
# INFO mode: tablica iz JSON-a
# -------------------------------------------------------------------------

def load_analysis_json(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _find_analysis_json_for_audio(audio_path: Path) -> Optional[Path]:
    """Pronađi analysis JSON za zadani audio.

    Primarna konvencija (nova):
        audio:  /.../Foo Bar.mp3
        json:   /.../.Foo Bar.analysis.json

    Podržani legacy kandidati (radi kompatibilnosti sa starim runovima):
        - Foo Bar.mp3.analysis.json
        - Foo Bar.analysis.json
        - .Foo Bar.mp3.analysis.json
    """
    suffix = getattr(ANALYSIS, "analysis_suffix", ".analysis.json")
    base_dir = audio_path.parent
    base_name = audio_path.stem

    candidates = [
        base_dir / f".{base_name}{suffix}",              # nova konvencija (skriven, bez ekstenzije)
        base_dir / f"{audio_path.name}{suffix}",         # legacy: track.mp3.analysis.json
        base_dir / f"{base_name}{suffix}",               # legacy: track.analysis.json
        base_dir / f".{audio_path.name}{suffix}",        # legacy: .track.mp3.analysis.json
    ]

    for c in candidates:
        if c.exists():
            return c
    return None



def _collect_audio_files(base: Path) -> List[Path]:
    exts = set(e.lower() for e in getattr(ANALYSIS, "supported_exts", (".flac", ".wav", ".mp3", ".m4a", ".ogg")))
    files: List[Path] = []
    for p in base.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            files.append(p)
    return sorted(files)


def _format_table(rows: List[List[str]], headers: List[str]) -> str:
    cols = len(headers)
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i in range(cols):
            col_widths[i] = max(col_widths[i], len(row[i]))

    def fmt_row(row: List[str]) -> str:
        return " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row))

    sep = "-+-".join("-" * w for w in col_widths)
    lines = [fmt_row(headers), sep]
    for r in rows:
        lines.append(fmt_row(r))
    return "\n".join(lines)


def info_for_paths(paths: List[Path]) -> None:
    analyses: List[Dict] = []
    for audio in paths:
        jpath = _find_analysis_json_for_audio(audio)
        if not jpath:
            continue
        try:
            analyses.append(load_analysis_json(jpath))
        except Exception:
            continue

    if not analyses:
        print("Nema pronađenih .analysis.json datoteka za zadane putanje.")
        return

    # Statistika
    total = len(paths)
    have = len(analyses)
    print(f"Analizirano JSON-a: {have}/{total}")
    durations = [a["features"]["duration"] for a in analyses if "features" in a]
    if durations:
        print(f"Prosječno trajanje: {sum(durations)/len(durations):.1f} s")
    print()

    # Tablica
    headers = [
        "File",
        "Dur(s)",
        "BPM",
        "Key",
        "Val",
        "Aro",
        "Energy",
        "Genre",
        "Alt1",
        "LeadInstr",
        "Bass",
        "Drums",
    ]
    rows: List[List[str]] = []
    for a in analyses:
        f = a.get("features", {})
        g = a.get("genre", {})
        m = a.get("mood", {})
        ins = a.get("instruments", {})

        rows.append([
            a.get("file", "")[:40],
            f"{f.get('duration', 0):.1f}",
            f"{f.get('tempo', 0):.1f}",
            f.get("key", ""),
            f"{m.get('valence', 0):.2f}",
            f"{m.get('arousal', 0):.2f}",
            f"{f.get('energy', 0):.2f}",
            g.get("primary", ""),
            (g.get("alt_1") or "")[:12],
            (ins.get("lead_instrument") or "")[:12],
            (ins.get("bass_type") or "")[:12],
            (ins.get("drums_pattern") or "")[:12],
        ])

    print(_format_table(rows, headers))


# -------------------------------------------------------------------------
# Sažetak per pjesmi (nakon analize)
# -------------------------------------------------------------------------

def print_track_summary(analysis: AnalysisJSON, json_path: Path, elapsed_sec: float) -> None:
    f = analysis.features
    g = analysis.genre
    m = analysis.mood
    ins = analysis.instruments

    print("  Sažetak analize:")
    print(f"    Vrijeme obrade : {elapsed_sec:.2f} s")
    print(f"    JSON           : {json_path}")
    print(f"    Trajanje       : {f.duration:.1f} s @ {f.sample_rate} Hz")
    print(f"    Tempo / Key    : {f.tempo:.1f} BPM, {f.key}")
    print(f"    Energy / Beat  : {f.energy:.2f}  |  beat_density={f.beat_density:.3f}")
    print(f"    Žanr           : {g.primary} (alt: {g.alt_1 or '-'}, conf={g.confidence:.2f})")
    print(f"    Mood           : {m.tag} (val={m.valence:.2f}, aro={m.arousal:.2f})")
    print(f"    Instrumenti    : lead={ins.lead_instrument or '-'}, bass={ins.bass_type or '-'}, drums={ins.drums_pattern or '-'}")


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audio_analyze",
        description="Full audio analiza (CLAP + Librosa + zero-shot jazz žanrovi/mood/instrumenti).",
    )
    parser.add_argument("--path", type=str, help="Put do pojedinačne audio datoteke ili foldera")
    parser.add_argument("--folder", type=str, help="Root folder za rekurzivnu analizu")
    parser.add_argument("--info", action="store_true", help="Umjesto analize, prikaz informacija iz .analysis.json")
    parser.add_argument("--overwrite", action="store_true", help="Prisili ponovno računanje analize i overwrite JSON-a")

    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.path and not args.folder:
        parser.error("Moraš zadati --path ili --folder (ili oba).")

    targets: List[Path] = []

    if args.path:
        p = Path(args.path)
        if p.is_dir():
            targets.extend(_collect_audio_files(p))
        else:
            targets.append(p)

    if args.folder:
        base = Path(args.folder)
        if not base.exists():
            parser.error(f"--folder ne postoji: {base}")
        targets.extend(_collect_audio_files(base))

    # Ukloni duplikate
    seen = set()
    uniq_targets: List[Path] = []
    for t in targets:
        t_res = t.resolve()
        if t_res not in seen:
            uniq_targets.append(t_res)
            seen.add(t_res)

    if args.info:
        info_for_paths(uniq_targets)
        return 0

    # Analiza
    root = BASE_MUSIC_PATH if args.folder is None else Path(args.folder).resolve()
    print(f"Root za rel_path: {root}")

    total = len(uniq_targets)
    if total == 0:
        print("Nema audio datoteka za analizu.")
        return 0

    for idx, audio in enumerate(uniq_targets, start=1):
        try:
            jpath_existing = _find_analysis_json_for_audio(audio)
            if jpath_existing and not args.overwrite:
                print(f"[{idx}/{total}] Preskačem (već postoji JSON): {audio}")
                continue

            print(f"[{idx}/{total}] Analiziram: {audio}")
            t0 = time.perf_counter()
            analysis = analyze_file(audio, root=root)
            out_json = write_analysis_json(analysis, audio)
            elapsed = time.perf_counter() - t0
            print(f"  → zapisano: {out_json}")
            print_track_summary(analysis, out_json, elapsed)
        except KeyboardInterrupt:
            print("\nPrekinuto od strane korisnika.")
            return 1
        except Exception as e:
            print(f"  ! Greška pri analizi {audio}: {e}", file=sys.stderr)

    print("Gotovo.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
