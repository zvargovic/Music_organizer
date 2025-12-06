from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

# Pokušaj uvesti config, ali nemoj srušiti skriptu ako ne postoji
try:
    import config  # type: ignore
except Exception:
    config = None  # type: ignore


AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".wave"}


def get_music_root() -> str | None:
    """Vrati root iz configa, ako postoji."""
    if config is None:
        return None
    # preferiraj get_music_root() ako postoji
    if hasattr(config, "get_music_root"):
        try:
            return config.get_music_root()  # type: ignore
        except Exception:
            return None
    # fallback na MUSIC_ROOT ili slično ime
    for attr in ("MUSIC_ROOT", "MUSIC_BASE", "MUSIC_PATH"):
        if hasattr(config, attr):
            val = getattr(config, attr)
            if isinstance(val, str):
                return val
    return None


def iter_audio_files(path: Path) -> list[Path]:
    """Vrati listu audio datoteka za obradu (file ili rekurzivni folder)."""
    if path.is_file():
        if path.suffix.lower() in AUDIO_EXTS:
            return [path]
        else:
            print(f"[UPOZORENJE] Nije audio datoteka, preskačem: {path}")
            return []
    if path.is_dir():
        files: list[Path] = []
        for p in path.rglob("*"):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                files.append(p)
        return sorted(files)
    print(f"[GREŠKA] Putanja ne postoji: {path}")
    return []


def load_json(path: Path, label: str) -> object | None:
    """Učitaj JSON. Vraća Python objekt (dict/list/str...). Ne ruši skriptu."""
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
    except FileNotFoundError:
        print(f"  [GREŠKA] {label}: datoteka ne postoji: {path}")
        return None
    except Exception as e:
        print(f"  [GREŠKA] {label}: ne mogu pročitati JSON {path}: {e}")
        return None

    # Ako je string koji možda sadrži JSON, pokušaj još jednom
    if isinstance(obj, str):
        try:
            inner = json.loads(obj)
            obj = inner
        except Exception:
            # ako ne uspije, ostavi string kakav jest
            pass

    return obj


def safe_get_dict(obj: object, label: str) -> dict | None:
    """Vrati obj ako je dict, inače ispiši grešku i vrati None."""
    if isinstance(obj, dict):
        return obj
    print(f"  [GREŠKA] {label} JSON nije dict nego {type(obj).__name__}; preskačem ovu pjesmu.")
    return None


def safe_get_file_hash(obj: object) -> str | None:
    """Sigurno izvuci file.hash_sha256 iz JSON-a, bez rušenja."""
    if not isinstance(obj, dict):
        return None
    file_section = obj.get("file")
    if not isinstance(file_section, dict):
        return None
    val = file_section.get("hash_sha256")
    return val if isinstance(val, str) else None


def build_final_json(spotify: dict, audio: dict, audio_json_path: Path, spotify_json_path: Path) -> dict:
    """
    Konstruira finalni JSON objekt iz spotify + audio analiza JSON-ova.

    Pravila za "file" blok:
    - Osnovni izvor je spotify["file"] (match modul) jer tamo imamo hash_sha256, path, size, mtime...
    - Zatim dodajemo sva polja iz audio["file"] koja još ne postoje u tom dictu.
    """
    file_info_spot = spotify.get("file")
    if not isinstance(file_info_spot, dict):
        file_info_spot = {}

    file_info = dict(file_info_spot)  # kopija

    file_info_audio = audio.get("file")
    if isinstance(file_info_audio, dict):
        for k, v in file_info_audio.items():
            if k not in file_info:
                file_info[k] = v

    final_obj: dict = {
        "schema": {
            "type": "track_final",
            "version": 1,
            "sources": {
                "spotify": spotify.get("schema"),
                "audio": audio.get("schema"),
            },
        },
        "file": file_info,
        "local_tags": spotify.get("local_tags") or audio.get("local_tags") or {},
        "spotify": spotify.get("spotify") or {},
        "match": spotify.get("match") or {},
        "audio": audio.get("audio") or {},
        "features": audio.get("features") or {},
        "genre": audio.get("genre") or {},
        "mood": audio.get("mood") or {},
        "instruments": audio.get("instruments") or {},
        "merge": {
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "audio_json": str(audio_json_path),
            "spotify_json": str(spotify_json_path),
        },
    }
    return final_obj


def print_track_summary(final_obj: dict, final_path: Path, elapsed: float) -> None:
    """Ispis sažetka za jednu pjesmu – hash, Spotify, žanr, mood, instrumenti."""
    file_info = final_obj.get("file") or {}
    if not isinstance(file_info, dict):
        file_info = {}
    features = final_obj.get("features") or {}
    genre = final_obj.get("genre") or {}
    mood = final_obj.get("mood") or {}
    instruments = final_obj.get("instruments") or {}
    spotify = final_obj.get("spotify") or {}

    if not isinstance(features, dict):
        features = {}
    if not isinstance(genre, dict):
        genre = {}
    if not isinstance(mood, dict):
        mood = {}
    if not isinstance(instruments, dict):
        instruments = {}
    if not isinstance(spotify, dict):
        spotify = {}

    duration = features.get("duration")
    sr = features.get("sample_rate")
    tempo = features.get("tempo")
    key = features.get("key")
    energy = features.get("energy")
    beat_density = features.get("beat_density")

    primary = genre.get("primary")
    alt_1 = genre.get("alt_1")
    conf = genre.get("confidence")

    valence = mood.get("valence")
    arousal = mood.get("arousal")
    mood_tag = mood.get("tag")

    lead = instruments.get("lead_instrument")
    bass = instruments.get("bass_type")
    drums = instruments.get("drums_pattern")

    hash_sha256 = file_info.get("hash_sha256")
    file_path = file_info.get("path")
    stem = file_info.get("stem") or (Path(file_path).stem if isinstance(file_path, str) else None)

    spot_id = spotify.get("id")
    spot_url = spotify.get("url")

    print(f"  → zapisano: {final_path}")
    print(f"  Sažetak finalnog zapisa:")
    print(f"    Vrijeme merge-a : {elapsed:.2f} s")
    if file_path:
        print(f"    Datoteka        : {file_path}")
    if stem:
        print(f"    Naslov          : {stem}")
    if hash_sha256:
        print(f"    Hash (sha256)   : {hash_sha256}")
    if spot_id or spot_url:
        print(f"    Spotify ID / URL: {spot_id}  |  {spot_url}")
    if duration is not None and sr is not None:
        print(f"    Trajanje        : {duration:.1f} s @ {sr} Hz")
    if tempo is not None or key is not None:
        print(f"    Tempo / Key     : {tempo:.1f} BPM, {key}")
    if energy is not None or beat_density is not None:
        print(f"    Energy / Beat   : {energy:.2f}  |  beat_density={beat_density:.3f}")
    if primary or alt_1 or conf is not None:
        print(f"    Žanr            : {primary} (alt: {alt_1}, conf={conf:.2f})")
    if mood_tag or (valence is not None) or (arousal is not None):
        print(f"    Mood            : {mood_tag} (val={valence:.2f}, aro={arousal:.2f})")
    if lead or bass or drums:
        print(f"    Instrumenti     : lead={lead}, bass={bass}, drums={drums}")


def process_track(audio_path: Path, force: bool, dry_run: bool):
    """
    Obradi jednu audio datoteku.
    status ∈ {
      'merged', 'skipped_final_exists',
      'missing_audio_json', 'missing_spotify_json',
      'hash_mismatch', 'error'
    }
    """
    parent = audio_path.parent
    stem = audio_path.stem

    # Podrška za dva formata imena audio JSON-a:
    #  1) NOVI:  .<stem>.analysis.json
    #  2) STARI: <filename>.mp3.analysis.json
    new_audio_json = parent / f".{stem}.analysis.json"
    old_audio_json = Path(str(audio_path) + ".analysis.json")

    if new_audio_json.exists():
        audio_json_path = new_audio_json
    elif old_audio_json.exists():
        audio_json_path = old_audio_json
    else:
        # preferiramo novi naziv u porukama / budućim generacijama
        audio_json_path = new_audio_json

    spotify_json_path = parent / f".{stem}.spotify.json"
    final_json_path = parent / f".{stem}.final.json"

    info = {
        "audio": str(audio_path),
        "audio_json": str(audio_json_path),
        "spotify_json": str(spotify_json_path),
        "final_json": str(final_json_path),
    }

    if final_json_path.exists() and not force:
        print(f"[SKIP] Već postoji final JSON, preskačem: {audio_path}")
        return "skipped_final_exists", info

    # Provjera postojanja JSON-ova
    if not audio_json_path.exists():
        print(f"[DORADA] Nedostaje audio analiza (.analysis.json): {audio_json_path}")
        print("         → pokreni audio_analyze.py za ovu pjesmu.")
        return "missing_audio_json", info

    if not spotify_json_path.exists():
        print(f"[DORADA] Nedostaje Spotify JSON (.stem.spotify.json): {spotify_json_path}")
        print("         → pokreni match.py za ovu pjesmu.")
        return "missing_spotify_json", info

    spotify_raw = load_json(spotify_json_path, "Spotify")
    audio_raw = load_json(audio_json_path, "Audio")

    spotify_obj = safe_get_dict(spotify_raw, "Spotify")
    audio_obj = safe_get_dict(audio_raw, "Audio")

    if spotify_obj is None or audio_obj is None:
        # već je ispisana greška u safe_get_dict
        return "error", info

    # Sigurno čitanje hash vrijednosti
    hash_spot = safe_get_file_hash(spotify_obj)
    hash_audio = safe_get_file_hash(audio_obj)
    if hash_spot and hash_audio and hash_spot != hash_audio:
        print(f"[UPOZORENJE] Hash mismatch između Spotify i audio JSON-a za: {audio_path}")
        print(f"            spotify: {hash_spot}")
        print(f"            audio  : {hash_audio}")
        print("            → preporuka: ponovo pokrenuti match.py i/ili audio_analyze.py.")
        return "hash_mismatch", info

    t0 = time.time()
    final_obj = build_final_json(spotify_obj, audio_obj, audio_json_path, spotify_json_path)
    elapsed = time.time() - t0

    if not dry_run:
        try:
            with final_json_path.open("w", encoding="utf-8") as f:
                json.dump(final_obj, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[GREŠKA] Ne mogu zapisati final JSON {final_json_path}: {e}")
            return "error", info

    print_track_summary(final_obj, final_json_path, elapsed)
    return "merged", info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="modules.merge",
        description="Merge modul — spajanje .spotify.json i .analysis.json u .final.json",
    )
    parser.add_argument(
        "--path",
        required=True,
        help="Putanja do audio datoteke ili foldera s glazbom.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ponovno generiraj .final.json čak i ako već postoji.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ne zapisuj final JSON, samo pokaži što bi se napravilo.",
    )

    args = parser.parse_args(argv)

    root = get_music_root()
    if root:
        print(f"Root za rel_path: {root}")
    else:
        print("Root za rel_path: (nije definiran u config.py)")

    base_path = Path(args.path)

    audio_files = iter_audio_files(base_path)
    if not audio_files:
        print("Nema audio datoteka za obradu.")
        return 1

    total = len(audio_files)
    print(f"Pronađeno audio datoteka: {total}")

    stats = {
        "merged": 0,
        "skipped_final_exists": 0,
        "missing_audio_json": 0,
        "missing_spotify_json": 0,
        "hash_mismatch": 0,
        "error": 0,
    }

    t_start = time.time()
    for idx, audio_path in enumerate(audio_files, start=1):
        print(f"[{idx}/{total}] Spajam: {audio_path}")
        status, _info = process_track(audio_path, force=args.force, dry_run=args.dry_run)
        if status in stats:
            stats[status] += 1
        else:
            stats["error"] += 1

    t_total = time.time() - t_start
    print("\n=== Statistika merge modula ===")
    print(f"  Ukupno pjesama        : {total}")
    print(f"  Uspješno spojenih     : {stats['merged']}")
    print(f"  Preskočeno (final)    : {stats['skipped_final_exists']}")
    print(f"  Za doradu (audio)     : {stats['missing_audio_json']}")
    print(f"  Za doradu (match)     : {stats['missing_spotify_json']}")
    print(f"  Hash mismatch         : {stats['hash_mismatch']}")
    print(f"  Greške pri obradi     : {stats['error']}")
    print(f"  Ukupno vrijeme obrade : {t_total:.2f} s")
    print("Gotovo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
