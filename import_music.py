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

import datetime
from pathlib import Path
import argparse
import os
import sys
import time
import traceback
import subprocess
import sqlite3
from dataclasses import dataclass, asdict
from typing import Iterable, List, Optional


# ---------------------------------------------------------------------------
# ANSI boje + helperi za progres
# ---------------------------------------------------------------------------

COLOR_YELLOW  = "\033[33m"
COLOR_MAGENTA = "\033[35m"
COLOR_BLUE    = "\033[34m"
COLOR_RESET   = "\033[0m"


def format_track_label(path: Optional[str]) -> str:
    """Vrati samo ime file-a iz cijele putanje."""
    if not path:
        return ""
    try:
        return os.path.basename(path)
    except Exception:
        return str(path)


def _get_db_path_from_config() -> Path:
    """Pokušaj izvući path baze iz modules.config; fallback na database/tracks.db."""
    try:
        from modules import config as cfg  # type: ignore[attr-defined]
    except Exception:
        return Path("database/tracks.db")

    if hasattr(cfg, "DB_PATH"):
        return Path(getattr(cfg, "DB_PATH"))
    if hasattr(cfg, "DB_FILE"):
        return Path(getattr(cfg, "DB_FILE"))
    if hasattr(cfg, "get_main_db_path"):
        try:
            return Path(cfg.get_main_db_path())  # type: ignore[misc]
        except Exception:
            pass
    return Path("database/tracks.db")


def get_tracks_in_db() -> int:
    """Vrati broj zapisa u tablici tracks; ako ne uspije, vrati 0."""
    try:
        db_path = _get_db_path_from_config()
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM tracks")
        row = cur.fetchone()
        conn.close()
        if not row or row[0] is None:
            return 0
        return int(row[0])
    except Exception:
        return 0


def print_progress(processed: int,
                   total: int,
                   tracks_in_db: int,
                   current_path: Optional[str] = None) -> None:
    """
    Ispiši osnovnu statistiku + progress bar u jednoj liniji.

    Primjer:
      Obrađujem: [37/6000] Track.mp3   (žuto)
      Zapisa u bazi: 37               (ljubičasto)
      12% [#####...................] 100% (plavo)
    """
    if total <= 0:
        return

    ratio = processed / total if total else 0.0
    if ratio < 0.0:
        ratio = 0.0
    if ratio > 1.0:
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
    # \r da prepišemo istu liniju, bez scrollanja
    sys.stderr.write("\r" + msg)
    sys.stderr.flush()


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

_IMPORT_LOG_FILE = None  # lazy-opened import log file handle


def log(msg: str) -> None:
    """Log helper: piše u stderr i u logs/import/*.log (ako je moguće)."""
    line = msg.rstrip("\n")
    # 1) stderr (osnovne informacije)
    sys.stderr.write(line + "\n")
    sys.stderr.flush()
    # 2) file log
    global _IMPORT_LOG_FILE
    try:
        base_dir = Path(__file__).resolve().parent
        log_dir = base_dir / "logs" / "import"
        log_dir.mkdir(parents=True, exist_ok=True)
        if _IMPORT_LOG_FILE is None:
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            log_file_path = log_dir / f"import_{ts}.log"
            _IMPORT_LOG_FILE = log_file_path.open("a", encoding="utf-8")
        _IMPORT_LOG_FILE.write(line + "\n")
        _IMPORT_LOG_FILE.flush()
    except Exception:
        # Ne ruši importer zbog problema sa logom
        pass


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
    try:
        return os.path.exists(path)
    except OSError:
        return False


def iter_audio_files(base_path: str) -> Iterable[str]:
    """Generator koji rekurzivno vrati sve audio datoteke."""
    for root, _, files in os.walk(base_path):
        for name in files:
            full = os.path.join(root, name)
            if is_audio_file(full):
                yield full


# ---------------------------------------------------------------------------
# Spotify throttle
# ---------------------------------------------------------------------------

_last_spotify_call: float = 0.0
_spotify_call_count: int = 0


def _throttle_spotify_if_needed() -> None:
    global _last_spotify_call
    now = time.time()
    delta = now - _last_spotify_call
    if delta < MIN_SPOTIFY_INTERVAL:
        time.sleep(MIN_SPOTIFY_INTERVAL - delta)
    _last_spotify_call = time.time()


# ---------------------------------------------------------------------------
# Wrapperi za module: MATCH / AUDIO / MERGE / LOAD
# ---------------------------------------------------------------------------

def run_match(audio_path: str, dry_run: bool = False) -> bool:
    """Pokreni MATCH za jedan track (uvijek CLI stil)."""
    global _spotify_call_count

    if dry_run:
        log(f"[DRY] MATCH  {audio_path}")
        return False

    _throttle_spotify_if_needed()

    try:
        from modules import match as match_mod  # type: ignore[attr-defined]
        if hasattr(match_mod, "match_track"):
            log(f"[MATCH] (func) {audio_path}")
            match_mod.match_track(audio_path)  # type: ignore[call-arg]
        else:
            log(f"[MATCH] (cli)  {audio_path}")
            subprocess.run(
                [sys.executable, "-m", "modules.match", "--path", audio_path],
                check=True,
            )
    except Exception:
        raise
    finally:
        _spotify_call_count += 1

    return True


def run_audio_analyze(audio_path: str, dry_run: bool = False) -> bool:
    """Pokreni AUDIO ANALYZE za jedan track (CLI stil, log u file)."""
    if dry_run:
        log(f"[DRY] AUDIO {audio_path}")
        return False

    cmd = [sys.executable, "-m", "modules.audio_analyze", "--path", audio_path]
    log(f"[AUDIO] (cli) {audio_path}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.stdout:
        log(proc.stdout.rstrip("\n"))
    if proc.stderr:
        log(proc.stderr.rstrip("\n"))
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr)

    return True


def run_merge(audio_path: str, dry_run: bool = False) -> bool:
    """Pokreni MERGE za jedan track (CLI stil, log u file)."""
    if dry_run:
        log(f"[DRY] MERGE {audio_path}")
        return False

    cmd = [sys.executable, "-m", "modules.merge", "--path", audio_path]
    log(f"[MERGE] (cli) {audio_path}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.stdout:
        log(proc.stdout.rstrip("\n"))
    if proc.stderr:
        log(proc.stderr.rstrip("\n"))
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr)

    return True


def run_load(audio_path: str, final_json: str, dry_run: bool = False) -> bool:
    """Pokreni LOAD za jedan track (CLI stil, log u file)."""
    if dry_run:
        log(f"[DRY] LOAD  {final_json}")
        return False

    cmd = [sys.executable, "-m", "modules.load", "--path", audio_path]
    log(f"[LOAD] (cli) {final_json}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.stdout:
        log(proc.stdout.rstrip("\n"))
    if proc.stderr:
        log(proc.stderr.rstrip("\n"))
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr)

    return True


# ---------------------------------------------------------------------------
# Per-track pipeline
# ---------------------------------------------------------------------------

def process_track(
    audio_path: str,
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
        log(f"[ERR] MATCH: {tr.error}")
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
        log(f"[ERR] AUDIO: {tr.error}")
        return tr

    # 3) MERGE
    try:
        if not skip_merge:
            need_merge = force_merge or not file_exists(final_json)
            if need_merge:
                tr.merged = run_merge(audio_path, dry_run=dry_run)
            else:
                log(f"[SKIP] MERGE (postoji {final_json})")
        else:
            log("[SKIP] MERGE (flag)")
    except Exception as e:
        tr.failed_stage = "MERGE"
        tr.error = "".join(traceback.format_exception_only(type(e), e)).strip()
        log(f"[ERR] MERGE: {tr.error}")
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
        log(f"[ERR] LOAD: {tr.error}")
        return tr

    return tr


# ---------------------------------------------------------------------------
# Argparse / main
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Glavni import pipeline za lokalnu kolekciju.")
    p.add_argument(
        "--base-path",
        required=True,
        help="Root direktorij gdje je muzika (Artist/Year/Album/Track).",
    )
    p.add_argument(
        "--max-tracks",
        type=int,
        default=None,
        help="Max broj pjesama za obradu u jednom run-u (default: sve).",
    )
    p.add_argument(
        "--force-match",
        action="store_true",
        help="Forsiraj MATCH čak i ako postoji .spotify.json.",
    )
    p.add_argument(
        "--force-audio",
        action="store_true",
        help="Forsiraj AUDIO analiza čak i ako postoji .analysis.json.",
    )
    p.add_argument(
        "--force-merge",
        action="store_true",
        help="Forsiraj MERGE čak i ako postoji .final.json.",
    )
    p.add_argument("--skip-match", action="store_true", help="Preskoči MATCH fazu.")
    p.add_argument("--skip-audio", action="store_true", help="Preskoči AUDIO fazu.")
    p.add_argument("--skip-merge", action="store_true", help="Preskoči MERGE fazu.")
    p.add_argument("--skip-load", action="store_true", help="Preskoči LOAD fazu.")
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="Preskoči pjesme za koje već postoji .final.json i hash u bazi.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Ne diraj datoteke ni bazu – samo pokaži što bi se radilo.",
    )
    p.add_argument(
        "--info",
        action="store_true",
        help="Na kraju ispiši JSON sa statistikama (na stdout).",
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

    # Skeniranje audio fajlova sa spinnerom
    audio_files: List[str] = []
    spinner = "|/-\\"
    log("[INFO] Skeniram kolekciju...")
    for i, p in enumerate(iter_audio_files(base_path), start=1):
        audio_files.append(p)
        ch = spinner[i % len(spinner)]
        sys.stderr.write(f"\r[SCAN] {ch} Pronađeno: {i}")
        sys.stderr.flush()
    sys.stderr.write("\n")
    sys.stderr.flush()

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
        # PROGRESS BAR SA BOJAMA
        print_progress(stats.total, total_files, get_tracks_in_db(), audio_path)

    # nova linija nakon progres bara
    sys.stderr.write("\n")
    sys.stderr.flush()

    # završni summary
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
        info = asdict(stats)
        info["elapsed_sec"] = elapsed
        print(json.dumps(info, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    import json  # za info-output
    raise SystemExit(main())