
"""
Downloader modul za Z-Music Organizer.

Faza 2: batch + provjera postojećih fajlova + REALNI download preko spotdl.
- Radi CLI:
    track / album / artist / batch / info
- Implementirano:
    * "batch" učitava JSON
    * složi TrackTask listu
    * za svaki track:
        - izračuna target path (Artist/Year/Album/Artist - Title.ext)
        - provjeri postoji li već audio fajl (mp3/flac/m4a/ogg/wav)
        - u --dry-run modu:
              - samo logira što bi napravio
        - u realnom modu (bez --dry-run):
              - ako ne postoji → pozove spotdl u TMP_DIR
              - premjesti fajl u target folder
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Pretpostavka: config.py je u project rootu i sadrži ove simbole.
try:
    from config import (
        get_downloader_log_dir,
        get_downloader_tmp_dir,
        get_downloader_batch_dir,
        get_default_music_root,
    )
except ImportError as exc:
    print("[FATAL] Nije moguće importati downloader config iz config.py:", exc, file=sys.stderr)
    sys.exit(1)


AUDIO_EXTS = [".mp3", ".flac", ".m4a", ".ogg", ".wav"]


@dataclass
class TrackTask:
    """Jedan planirani download zadatak za track."""
    spotify_id: str
    spotify_url: Optional[str]
    artist: str
    album: str
    album_year: Optional[int]
    track_name: str
    disc_number: Optional[int] = None
    track_number: Optional[int] = None

    def target_rel_path(self) -> Path:
        """
        Relativni path unutar base_path gdje bi fajl trebao završiti.
        Folder struktura: Artist/Year/Album/Artist - Title.ext (ext se još ne zna).
        """
        year_str = str(self.album_year) if self.album_year is not None else "0000"
        filename = f"{self.artist} - {self.track_name}"
        return Path(self.artist) / year_str / self.album / filename

    def spotify_track_url(self) -> str:
        """Vrati punu Spotify URL za ovaj track."""
        if self.spotify_url:
            return self.spotify_url
        return f"https://open.spotify.com/track/{self.spotify_id}"


def setup_logging(log_level: str) -> None:
    """Postavi logging konfiguraciju."""
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    # Kreiraj log direktorij ako je moguće
    log_dir = Path(get_downloader_log_dir())
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"download_{time.strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logging.info("Downloader start")
    logging.info("Log file: %s", log_file)


def resolve_base_path(cli_base_path: Optional[str]) -> Path:
    """
    Odredi base path za glazbenu kolekciju.
    Prioritet:
      1. --base-path iz CLI-ja (ako je dan)
      2. get_default_music_root() iz config.py (env varijabla)
      3. ako ništa od toga, baca se FATAL i prekida program.
    """
    if cli_base_path:
        base = Path(cli_base_path).expanduser()
        logging.info("Base path (CLI): %s", base)
        return base

    env_base = get_default_music_root()
    if env_base is not None:
        logging.info("Base path (env ZMUSIC_MUSIC_ROOT): %s", env_base)
        return env_base

    logging.error(
        "Base path nije zadan. "
        "Dodaj --base-path /put/do/Music ili postavi ZMUSIC_MUSIC_ROOT u env."
    )
    print(
        "[FATAL] Base path nije definiran.\n"
        "Dodaj --base-path /put/do/Music ili postavi ZMUSIC_MUSIC_ROOT u environment.",
        file=sys.stderr,
    )
    sys.exit(1)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Dodaj globalne/common argumente svim subkomandama."""
    parser.add_argument(
        "--base-path",
        type=str,
        default=None,
        help="Osnovni folder glazbene kolekcije (ako nije zadano, koristi env ZMUSIC_MUSIC_ROOT).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ne skidaj ništa, samo pokaži što bi se radilo.",
    )
    parser.add_argument(
        "--max-tracks",
        type=int,
        default=None,
        help="Maksimalan broj trackova koji će se obraditi (za testiranje).",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Na kraju prikaži sažetak (statistiku).",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="download",
        description="Downloader modul za Z-Music Organizer.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level (default: INFO).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # track
    p_track = subparsers.add_parser("track", help="Skini jedan track po ID-u ili URL-u.")
    add_common_args(p_track)
    group = p_track.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", type=str, help="Spotify track ID")
    group.add_argument("--url", type=str, help="Spotify track URL")
    p_track.set_defaults(func=cmd_track)

    # album
    p_album = subparsers.add_parser("album", help="Skini cijeli album po ID-u ili URL-u.")
    add_common_args(p_album)
    group_a = p_album.add_mutually_exclusive_group(required=True)
    group_a.add_argument("--id", type=str, help="Spotify album ID")
    group_a.add_argument("--url", type=str, help="Spotify album URL")
    p_album.set_defaults(func=cmd_album)

    # artist
    p_artist = subparsers.add_parser("artist", help="Skini sve ili nove albume nekog artista.")
    add_common_args(p_artist)
    group_art = p_artist.add_mutually_exclusive_group(required=True)
    group_art.add_argument("--id", type=str, help="Spotify artist ID")
    group_art.add_argument("--url", type=str, help="Spotify artist URL")
    p_artist.add_argument(
        "--mode",
        choices=["all", "new"],
        default="all",
        help="all = svi albumi, new = pokušaj prepoznati samo nove albume (TODO).",
    )
    p_artist.set_defaults(func=cmd_artist)

    # batch
    p_batch = subparsers.add_parser("batch", help="Skini iz batch JSON liste.")
    add_common_args(p_batch)
    p_batch.add_argument(
        "--json",
        required=True,
        type=str,
        help="Path do batch JSON fajla koji sadrži listu trackova.",
    )
    p_batch.set_defaults(func=cmd_batch)

    # info
    p_info = subparsers.add_parser("info", help="Prikaži konfiguraciju downloadera.")
    # info ne treba common args; samo outputa config
    p_info.set_defaults(func=cmd_info)

    return parser


# ---------------------------------------------------------------------
# Helperi za batch / download
# ---------------------------------------------------------------------

def find_existing_audio(base_without_ext: Path) -> Optional[Path]:
    """
    Provjeri postoji li već audio fajl za zadanu bazu imena.
    Traži ekstenzije iz AUDIO_EXTS.
    """
    for ext in AUDIO_EXTS:
        candidate = base_without_ext.with_suffix(ext)
        if candidate.is_file():
            return candidate
    return None


def perform_download(task: TrackTask, base_path: Path, tmp_dir: Path) -> Optional[Path]:
    """
    Izvrši stvarni download preko spotdl-a za zadani task.

    Vraća path do konačnog audio fajla u base_path ako uspije, inače None.
    """
    spotify_url = task.spotify_track_url()
    logging.info("  [DL] Pokrećem spotdl za URL: %s", spotify_url)

    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Output pattern za spotdl (u TMP dir)
    out_pattern = str(tmp_dir / "%(artist)s - %(title)s.%(ext)s")

    cmd = [
        "spotdl",
        spotify_url,
        "--output",
        out_pattern,
    ]

    logging.debug("  [DL] CMD: %s", " ".join(cmd))

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logging.error("  [DL-ERROR] spotdl nije pronađen u PATH-u.")
        return None
    except Exception as exc:  # noqa: BLE001
        logging.exception("  [DL-ERROR] Izuzetak pri pokretanju spotdl: %s", exc)
        return None

    if proc.returncode != 0:
        logging.error("  [DL-ERROR] spotdl vratio kod %s", proc.returncode)
        logging.debug("  [DL-STDOUT] %s", proc.stdout.strip())
        logging.debug("  [DL-STDERR] %s", proc.stderr.strip())
        return None

    # Pokušaj pronaći skinuti fajl u TMP diru
    base_name = f"{task.artist} - {task.track_name}"
    downloaded_file: Optional[Path] = None
    for ext in AUDIO_EXTS:
        candidate = tmp_dir / f"{base_name}{ext}"
        if candidate.is_file():
            downloaded_file = candidate
            break

    if downloaded_file is None:
        logging.error("  [DL-ERROR] Ne mogu pronaći output fajl za %s u %s", base_name, tmp_dir)
        logging.debug("  [DL-STDOUT] %s", proc.stdout.strip())
        logging.debug("  [DL-STDERR] %s", proc.stderr.strip())
        return None

    # Formiraj konačni target path
    target_no_ext = base_path / task.target_rel_path()
    target_dir = target_no_ext.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    final_target = target_no_ext.with_suffix(downloaded_file.suffix)

    try:
        shutil.move(str(downloaded_file), str(final_target))
    except Exception as exc:  # noqa: BLE001
        logging.exception("  [DL-ERROR] Ne mogu premjestiti %s u %s: %s", downloaded_file, final_target, exc)
        return None

    logging.info("  [DL-OK] Skinuto i premješteno u: %s", final_target)
    return final_target


# ---------------------------------------------------------------------
# Subcommand implementacije
# ---------------------------------------------------------------------

def cmd_track(args: argparse.Namespace) -> int:
    """Za sada samo skeleton: jedan track se tretira kao mini batch."""
    base_path = resolve_base_path(args.base_path)
    tmp_dir = Path(get_downloader_tmp_dir())
    logging.info("[TRACK] mode")
    logging.info("  input: id=%r url=%r", getattr(args, "id", None), getattr(args, "url", None))
    logging.info("  base_path: %s", base_path)

    # Minimalan skeleton: složimo jedan TrackTask s minimalnim podacima
    spotify_id = args.id if args.id is not None else ""
    spotify_url = args.url

    task = TrackTask(
        spotify_id=spotify_id,
        spotify_url=spotify_url,
        artist="Unknown Artist",
        album="Unknown Album",
        album_year=None,
        track_name="Unknown Track",
    )

    target_no_ext = base_path / task.target_rel_path()
    existing = find_existing_audio(target_no_ext)

    total = 1
    downloaded = 0
    skipped = 0
    failed = 0

    if existing is not None:
        logging.info("  [EXISTS] Već postoji audio fajl: %s", existing)
        skipped += 1
    else:
        if args.dry_run:
            logging.info("  [DRY-RUN] AUDIO NE POSTOJI → ovdje bi išao download.")
            skipped += 1
        else:
            result = perform_download(task, base_path, tmp_dir)
            if result is not None:
                downloaded += 1
            else:
                failed += 1

    if args.info:
        print_summary(
            total=total,
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            elapsed_sec=0.0,
        )
    return 0


def cmd_album(args: argparse.Namespace) -> int:
    """Skeleton: cijeli album (još bez stvarnog Spotify API)."""
    base_path = resolve_base_path(args.base_path)
    logging.info("[ALBUM] mode (kostur)")
    logging.info("  input: id=%r url=%r", getattr(args, "id", None), getattr(args, "url", None))
    logging.info("  base_path: %s", base_path)

    simulated_tracks = 10
    to_process = (
        min(simulated_tracks, args.max_tracks)
        if args.max_tracks is not None
        else simulated_tracks
    )
    logging.warning("ALBUM subcommand je još uvijek kostur — nema stvarni Spotify lookup.")
    if args.dry_run:
        logging.info("[DRY-RUN] Simuliram da bih obradio %d trackova za ovaj album.", to_process)
    else:
        logging.info("[NO-OP] Simulacija obrade %d trackova (bez pravog downloada).", to_process)

    if args.info:
        print_summary(
            total=to_process,
            downloaded=0,
            skipped=0,
            failed=0,
            elapsed_sec=0.0,
        )
    return 0


def cmd_artist(args: argparse.Namespace) -> int:
    """Skeleton: svi / novi albumi artista (još bez stvarnog Spotify API)."""
    base_path = resolve_base_path(args.base_path)
    logging.info("[ARTIST] mode (kostur)")
    logging.info("  input: id=%r url=%r mode=%s", getattr(args, "id", None), getattr(args, "url", None), args.mode)
    logging.info("  base_path: %s", base_path)

    simulated_albums = 3
    simulated_tracks_per_album = 8
    total_tracks = simulated_albums * simulated_tracks_per_album
    to_process = (
        min(total_tracks, args.max_tracks)
        if args.max_tracks is not None
        else total_tracks
    )

    logging.warning("ARTIST subcommand je još uvijek kostur — nema stvarni Spotify lookup.")
    logging.info(
        "[SIM] Pretpostavljam %d albuma × %d trackova = %d trackova (mode=%s).",
        simulated_albums,
        simulated_tracks_per_album,
        total_tracks,
        args.mode,
    )

    if args.dry_run:
        logging.info("[DRY-RUN] Simuliram da bih obradio %d trackova za ovog artista.", to_process)
    else:
        logging.info("[NO-OP] Simulacija obrade %d trackova (bez pravog downloada).", to_process)

    if args.info:
        print_summary(
            total=to_process,
            downloaded=0,
            skipped=0,
            failed=0,
            elapsed_sec=0.0,
        )
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    """Batch download iz JSON liste."""
    base_path = resolve_base_path(args.base_path)
    batch_path = Path(args.json).expanduser()
    tmp_dir = Path(get_downloader_tmp_dir())
    logging.info("[BATCH] mode")
    logging.info("  batch JSON: %s", batch_path)
    logging.info("  base_path: %s", base_path)

    if not batch_path.is_file():
        logging.error("Batch JSON ne postoji: %s", batch_path)
        return 1

    try:
        with batch_path.open("r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
    except Exception as exc:  # noqa: BLE001
        logging.exception("Ne mogu učitati batch JSON: %s", exc)
        return 1

    tracks_data = data.get("tracks", [])
    if not isinstance(tracks_data, list):
        logging.error("Neispravan format batch JSON-a: 'tracks' nije lista.")
        return 1

    tasks: List[TrackTask] = []
    for idx, item in enumerate(tracks_data, start=1):
        try:
            spotify_id = item["spotify_id"]
            artist = item["artist"]
            album = item["album"]
            album_year = item.get("album_year")
            track_name = item["track_name"]
            spotify_url = item.get("spotify_url")
            disc_number = item.get("disc_number")
            track_number = item.get("track_number")
        except KeyError as ke:
            logging.warning("Preskačem neispravan zapis #%d (nedostaje ključ %s).", idx, ke)
            continue

        task = TrackTask(
            spotify_id=spotify_id,
            spotify_url=spotify_url,
            artist=artist,
            album=album,
            album_year=album_year,
            track_name=track_name,
            disc_number=disc_number,
            track_number=track_number,
        )
        tasks.append(task)

    if not tasks:
        logging.warning("Batch lista je prazna ili neispravna — nema taskova za obradu.")
        if args.info:
            print_summary(total=0, downloaded=0, skipped=0, failed=0, elapsed_sec=0.0)
        return 0

    start = time.time()
    total = 0
    downloaded = 0
    skipped = 0
    failed = 0

    max_tracks = args.max_tracks if args.max_tracks is not None else len(tasks)
    logging.info("Planirano taskova: %d, max-tracks limit: %d", len(tasks), max_tracks)

    for i, task in enumerate(tasks, start=1):
        if total >= max_tracks:
            logging.info("Dosegnut max-tracks=%d, prekidam.", max_tracks)
            break

        rel_path = task.target_rel_path()
        target_no_ext = base_path / rel_path  # bez ekstenzije

        existing = find_existing_audio(target_no_ext)

        logging.info(
            "[TASK %d/%d] %s - %s → %s (spotify_id=%s)",
            i,
            len(tasks),
            task.artist,
            task.track_name,
            target_no_ext,
            task.spotify_id,
        )

        if existing is not None:
            logging.info("  [EXISTS] Već postoji audio fajl: %s", existing)
            skipped += 1
        else:
            if args.dry_run:
                logging.info("  [DRY-RUN] AUDIO NE POSTOJI → ovdje bi išao download.")
                skipped += 1
            else:
                result = perform_download(task, base_path, tmp_dir)
                if result is not None:
                    downloaded += 1
                else:
                    failed += 1

        total += 1

    elapsed = time.time() - start
    if args.info:
        print_summary(
            total=total,
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            elapsed_sec=elapsed,
        )
    return 0


def cmd_info(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Ispiši konfiguraciju relevantnu za downloader."""
    print("=== Downloader info ===")

    batch_dir = Path(get_downloader_batch_dir())
    tmp_dir = Path(get_downloader_tmp_dir())
    log_dir = Path(get_downloader_log_dir())

    print(f"BATCH_DIR:             {batch_dir}")
    print(f"TMP_DIR:               {tmp_dir}")
    print(f"LOG_DIR:               {log_dir}")

    env_base = get_default_music_root()
    print(f"Env ZMUSIC_MUSIC_ROOT: {env_base if env_base is not None else '(nije postavljen)'}")

    return 0


# ---------------------------------------------------------------------
# Helper za ispis sažetka
# ---------------------------------------------------------------------

def print_summary(
    total: int,
    downloaded: int,
    skipped: int,
    failed: int,
    elapsed_sec: float,
) -> None:
    """Ispiši sažetak u human-friendly obliku + JSON na kraju."""
    print("\n===== DOWNLOAD SUMMARY =====")
    print(f"Ukupno taskova    : {total}")
    print(f"Downloaded        : {downloaded}")
    print(f"Skipped           : {skipped}")
    print(f"Failed            : {failed}")
    print(f"Trajanje          : {elapsed_sec:.1f} s")

    summary = {
        "total": total,
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "elapsed_sec": elapsed_sec,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------
# main
# ---------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    setup_logging(args.log_level)

    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1

    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
