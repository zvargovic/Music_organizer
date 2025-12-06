#!/usr/bin/env python3
"""
import_music.py

Glavni import pipeline za lokalnu kolekciju:

    MATCH → AUDIO ANALYZE → MERGE → LOAD

- prolazi kroz cijeli --base-path
- za svaku audio datoteku pokreće per-track pipeline
- pokušava biti idempotentan preko skrivenih *.json fajlova
- ugrađena zaštita od Spotify flooda (lokalni throttle)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
import subprocess
from dataclasses import dataclass, asdict
from typing import Iterable, List, Optional


# ---------------------------------------------------------------------------
# Konstante za ekstenzije / JSON suffixe
# ---------------------------------------------------------------------------

AUDIO_EXTENSIONS = {".flac", ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".aiff"}

# Tvoja stvarna konvencija:
# /dir/.Track.spotify.json
# /dir/.Track.analysis.json
# /dir/.Track.final.json
SPOTIFY_SUFFIX = ".spotify.json"
AUDIO_SUFFIX   = ".analysis.json"
FINAL_SUFFIX   = ".final.json"

# Minimalni razmak izmedu Spotify poziva (sekunde)
MIN_SPOTIFY_INTERVAL = 1.0


# ---------------------------------------------------------------------------
# Pomoćne strukture
# ---------------------------------------------------------------------------

@dataclass
class TrackResult:
    path: str
    matched: bool = False
    analyzed: bool = False
    merged: bool = False
    loaded: bool = False
    failed_stage: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Stats:
    total: int = 0
    matched: int = 0
    analyzed: int = 0
    merged: int = 0
    loaded: int = 0
    failed: int = 0
    spotify_calls: int = 0

    def update_from_track(self, tr: TrackResult) -> None:
        self.total += 1
        if tr.matched:
            self.matched += 1
        if tr.analyzed:
            self.analyzed += 1
        if tr.merged:
            self.merged += 1
        if tr.loaded:
            self.loaded += 1
        if tr.failed_stage is not None:
            self.failed += 1


# ---------------------------------------------------------------------------
# Utility funkcije
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    """Jednostavan log na stderr (da stdout ostane čist ako ga neko parsira)."""
    sys.stderr.write(msg.rstrip() + "\n")
    sys.stderr.flush()


def is_audio_file(path: str) -> bool:
    _, ext = os.path.splitext(path)
    return ext.lower() in AUDIO_EXTENSIONS


def derive_stem(audio_path: str) -> str:
    """Vrati bazu bez ekstenzije.

    /foo/bar/Track.flac -> /foo/bar/Track
    """
    root, _ = os.path.splitext(audio_path)
    return root


def hidden_json_path(audio_path: str, suffix: str) -> str:
    """
    /foo/Track.flac + '.spotify.json' -> /foo/.Track.spotify.json
    """
    stem = derive_stem(audio_path)      # /foo/Track
    dir_, base = os.path.split(stem)    # '/foo', 'Track'
    hidden_base = "." + base            # '.Track'
    return os.path.join(dir_, hidden_base + suffix)


def newer_than(path_a: str, path_b: str) -> bool:
    """True ako je path_a noviji od path_b (oba moraju postojati)."""
    try:
        return os.path.getmtime(path_a) > os.path.getmtime(path_b)
    except OSError:
        return False


def file_exists(path: str) -> bool:
    return os.path.isfile(path)

# ---------------------------------------------------------------------------
# ANSI boje i progres bar
# ---------------------------------------------------------------------------

COLOR_YELLOW  = "\033[33m"
COLOR_MAGENTA = "\033[35m"
COLOR_BLUE    = "\033[34m"
COLOR_RESET   = "\033[0m"


def format_track_label(path: Optional[str]) -> str:
    """Vrati lijepi label za trenutačni track (samo ime file-a)."""
    if not path:
        return ""
    try:
        base = os.path.basename(path)
    except Exception:
        return str(path)
    return base


def print_progress(processed: int, total: int, tracks_in_db: int, current_path: Optional[str] = None) -> None:
    """Ispiši osnovnu statistiku + progress bar u jednoj liniji.

    Primjer:
      Obrađujem: [37/6000] Neki Track.mp3   (žuto)
      Zapisa u bazi: 37                     (ljubičasto)
      12% [#####......................] 100% (plavo)

    Ovdje je sve spojeno u jednu liniju da ekran što manje scrolla.
    """
    if total <= 0:
        return

    ratio = processed / total if total else 0.0
    if ratio < 0:
        ratio = 0.0
    if ratio > 1:
        ratio = 1.0

    bar_len = 35
    filled = int(bar_len * ratio)
    bar = "#" * filled + "." * (bar_len - filled)
    percent = int(ratio * 100)

    track_label = format_track_label(current_path)
    left = f"{COLOR_YELLOW}Obrađujem: [{processed}/{total}] {track_label}{COLOR_RESET}"
    mid  = f"{COLOR_MAGENTA}Zapisa u bazi: {tracks_in_db}{COLOR_RESET}"
    right = f"{COLOR_BLUE}{percent:3d}% [{bar}] 100%{COLOR_RESET}"

    msg = f"{left}  {mid}  {right}"
    sys.stderr.write("\r" + msg)
    sys.stderr.flush()



# ---------------------------------------------------------------------------
# Hookovi na postojeće module (match / analyze / merge / load)
# Pokušaj importati Python funkcije; fallback na `python -m ...`.
# ---------------------------------------------------------------------------

_last_spotify_call: float = 0.0  # za throttle
_spotify_call_count: int = 0


def _throttle_spotify_if_needed() -> None:
    global _last_spotify_call
    now = time.time()
    delta = now - _last_spotify_call
    if delta < MIN_SPOTIFY_INTERVAL:
        time.sleep(MIN_SPOTIFY_INTERVAL - delta)
    _last_spotify_call = time.time()


def run_match(audio_path: str, dry_run: bool = False) -> bool:
    """Pokreni MATCH za jedan track. Vraca True ako je stvarno odrađen novi match."""
    global _spotify_call_count

    if dry_run:
        log(f"[DRY] MATCH  {audio_path}")
        return False

    _throttle_spotify_if_needed()

    # 1) pokušaj direktnog importa funkcije
    try:
        from modules import match as match_mod  # type: ignore[attr-defined]
        if hasattr(match_mod, "match_track"):
            log(f"[MATCH] (func) {audio_path}")
            match_mod.match_track(audio_path)  # type: ignore[call-arg]
        else:
            # fallback: CLI stil
            log(f"[MATCH] (cli)  {audio_path}")
            subprocess.run(
                [sys.executable, "-m", "modules.match", "--path", audio_path],
                check=True,
            )
    except Exception:
        # Propusti grešku calleru
        raise
    finally:
        _spotify_call_count += 1

    return True


def run_audio_analyze(audio_path: str, dry_run: bool = False) -> bool:
    if dry_run:
        log(f"[DRY] AUDIO {audio_path}")
        return False

    try:
        from modules import audio_analyze as aa_mod  # type: ignore[attr-defined]
        if hasattr(aa_mod, "analyze_track"):
            log(f"[AUDIO] (func) {audio_path}")
            aa_mod.analyze_track(audio_path)  # type: ignore[call-arg]
        else:
            log(f"[AUDIO] (cli)  {audio_path}")
            subprocess.run(
                [sys.executable, "-m", "modules.audio_analyze", "--path", audio_path],
                check=True,
            )
    except Exception:
        raise

    return True


def run_merge(audio_path: str, dry_run: bool = False) -> bool:
    if dry_run:
        log(f"[DRY] MERGE {audio_path}")
        return False

    try:
        from modules import merge as merge_mod  # type: ignore[attr-defined]
        if hasattr(merge_mod, "merge_track"):
            log(f"[MERGE] (func) {audio_path}")
            stem = derive_stem(audio_path)
            merge_mod.merge_track(stem)  # type: ignore[call-arg]
        else:
            log(f"[MERGE] (cli)  {audio_path}")
            subprocess.run(
                [sys.executable, "-m", "modules.merge", "--path", audio_path],
                check=True,
            )
    except Exception:
        raise

    return True


def run_load(audio_path: str, final_json: str, dry_run: bool = False) -> bool:
    if dry_run:
        log(f"[DRY] LOAD  {final_json}")
        return False

    try:
        from modules import load as load_mod  # type: ignore[attr-defined]
        if hasattr(load_mod, "load_track"):
            log(f"[LOAD] (func) {final_json}")
            load_mod.load_track(final_json)  # type: ignore[call-arg]
        else:
            log(f"[LOAD] (cli)  {final_json}")
            subprocess.run(
                [sys.executable, "-m", "modules.load", "--path", audio_path],
                check=True,
            )
    except Exception:
        raise

    return True


# ---------------------------------------------------------------------------
# Per-track pipeline
# ---------------------------------------------------------------------------

def process_track(
    audio_path: str,
    *,
    force_match: bool = False,
    force_audio: bool = False,
    force_merge: bool = False,
    skip_match: bool = False,
    skip_audio: bool = False,
    skip_merge: bool = False,
    skip_load: bool = False,
    dry_run: bool = False,
) -> TrackResult:
    """
    MATCH → AUDIO → MERGE → LOAD za jedan audio fajl,
    s idempotentnim provjerama baziranima na skrivenim *.json datotekama.
    """
    tr = TrackResult(path=audio_path)

    spotify_json = hidden_json_path(audio_path, SPOTIFY_SUFFIX)
    audio_json   = hidden_json_path(audio_path, AUDIO_SUFFIX)
    final_json   = hidden_json_path(audio_path, FINAL_SUFFIX)

    log(f"\n=== TRACK === {audio_path}")

    # 1) MATCH
    try:
        if not skip_match:
            need_match = force_match or not file_exists(spotify_json)
            if need_match:
                tr.matched = run_match(audio_path, dry_run=dry_run)
            else:
                log(f"[SKIP] MATCH (postoji {spotify_json})")
        else:
            log("[SKIP] MATCH (flag)")
    except Exception as e:
        tr.failed_stage = "MATCH"
        tr.error = "".join(traceback.format_exception_only(type(e), e)).strip()
        log(f"[ERR] MATCH failed: {tr.error}")
        return tr

    # 2) AUDIO ANALYZE
    try:
        if not skip_audio:
            need_audio = force_audio or not file_exists(audio_json)
            if need_audio:
                tr.analyzed = run_audio_analyze(audio_path, dry_run=dry_run)
            else:
                log(f"[SKIP] AUDIO (postoji {audio_json})")
        else:
            log("[SKIP] AUDIO (flag)")
    except Exception as e:
        tr.failed_stage = "AUDIO"
        tr.error = "".join(traceback.format_exception_only(type(e), e)).strip()
        log(f"[ERR] AUDIO failed: {tr.error}")
        return tr

    # 3) MERGE
    try:
        if not skip_merge:
            need_merge = (
                force_merge
                or not file_exists(final_json)
                or (file_exists(spotify_json) and newer_than(spotify_json, final_json))
                or (file_exists(audio_json) and newer_than(audio_json, final_json))
            )
            if need_merge:
                tr.merged = run_merge(audio_path, dry_run=dry_run)
            else:
                log(f"[SKIP] MERGE (final je up-to-date: {final_json})")
        else:
            log("[SKIP] MERGE (flag)")
    except Exception as e:
        tr.failed_stage = "MERGE"
        tr.error = "".join(traceback.format_exception_only(type(e), e)).strip()
        log(f"[ERR] MERGE failed: {tr.error}")
        return tr

    # 4) LOAD
    try:
        if not skip_load:
            if file_exists(final_json):
                tr.loaded = run_load(audio_path, final_json, dry_run=dry_run)
            else:
                log(f"[WARN] LOAD preskočen – ne postoji {final_json}")
        else:
            log("[SKIP] LOAD (flag)")
    except Exception as e:
        tr.failed_stage = "LOAD"
        tr.error = "".join(traceback.format_exception_only(type(e), e)).strip()
        log(f"[ERR] LOAD failed: {tr.error}")
        return tr

    return tr


# ---------------------------------------------------------------------------
# Walking kolekcije
# ---------------------------------------------------------------------------

def iter_audio_files(base_path: str) -> Iterable[str]:
    """Rekurzivno yield-a sve audio fajlove unutar base_path."""
    for root, dirs, files in os.walk(base_path):
        # ignoriraj tipične skrivene foldere
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.startswith("."):
                continue
            full = os.path.join(root, name)
            if is_audio_file(full):
                yield full


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Import pipeline za lokalnu kolekciju (MATCH → AUDIO → MERGE → LOAD).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--base-path",
        required=True,
        help="Root folder gdje se nalazi muzika (Artist/Year/Album/Tracks).",
    )
    p.add_argument("--dry-run", action="store_true", help="Ne izvršava module, samo logira što bi radilo.")
    p.add_argument("--max-tracks", type=int, default=None, help="Opcionalni limit broja pjesama (za test).")

    # force / skip flagovi
    p.add_argument("--force-match", action="store_true")
    p.add_argument("--force-audio", action="store_true")
    p.add_argument("--force-merge", action="store_true")

    p.add_argument("--skip-match", action="store_true")
    p.add_argument("--skip-audio", action="store_true")
    p.add_argument("--skip-merge", action="store_true")
    p.add_argument("--skip-load", action="store_true")

    p.add_argument(
        "--info",
        action="store_true",
        help="Na kraju ispisi JSON sa statistikama.",
    )

    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    global _spotify_call_count

    args = parse_args(argv)

    base_path = os.path.abspath(args.base_path)
    if not os.path.isdir(base_path):
        log(f"[FATAL] base-path ne postoji ili nije direktorij: {base_path}")
        return 1

    log(f"[INFO] Import start — base-path={base_path}")
    t_start = time.time()

    stats = Stats()
    audio_files = sorted(iter_audio_files(base_path))
    total_files = len(audio_files)
    log(f"[INFO] Pronađeno audio fajlova: {total_files}")

    for idx, audio_path in enumerate(audio_files, start=1):
        if args.max_tracks is not None and idx > args.max_tracks:
            log(f"[INFO] max-tracks={args.max_tracks} dosegnut, prekidam.")
            break

        log(f"[FILE {idx}/{total_files}] {audio_path}")
        try:
            tr = process_track(
                audio_path,
                force_match=args.force_match,
                force_audio=args.force_audio,
                force_merge=args.force_merge,
                skip_match=args.skip_match,
                skip_audio=args.skip_audio,
                skip_merge=args.skip_merge,
                skip_load=args.skip_load,
                dry_run=args.dry_run,
            )
        except KeyboardInterrupt:
            log("\n[INTERRUPT] Korisnik prekinuo.")
            break
        except Exception as e:
            tr = TrackResult(
                path=audio_path,
                failed_stage="UNEXPECTED",
                error="".join(traceback.format_exception_only(type(e), e)).strip(),
            )
            log(f"[ERR] Neočekivana greška: {tr.error}")

        stats.update_from_track(tr)
        print_progress(stats.total, total_files, get_tracks_in_db(), audio_path)

    # zavrsni summary
    elapsed = time.time() - t_start
    stats.spotify_calls = _spotify_call_count

    log("\n===== IMPORT SUMMARY =====")
    log(f"Ukupno pjesama (processirane): {stats.total}")
    log(f"Matched:   {stats.matched}")
    log(f"Analyzed:  {stats.analyzed}")
    log(f"Merged:    {stats.merged}")
    log(f"Loaded:    {stats.loaded}")
    log(f"Failed:    {stats.failed}")
    log(f"Spotify calls (approx): {stats.spotify_calls}")
    log(f"Trajanje:  {elapsed:.1f} s")

    if args.info:
        # info output na stdout kao JSON (npr. za skripte / UI)
        import json
        info = asdict(stats)
        info["elapsed_sec"] = elapsed
        print(json.dumps(info, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())