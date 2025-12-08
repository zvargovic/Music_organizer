"""Download queue modul za Z-Music Organizer.

Ovaj modul je *orkestrator* iznad postojećeg `modules.download`.

- NE skida ništa sam, stvarni download radi `modules.download` (tvoj postojeći core).
- Čita batch JSON-ove koje generiraju download_gen_* skripte (ključ "tracks").
- Za svaki batch poziva:

    python -m modules.download batch --json <file> --base-path <root> --info [--dry-run]

Podržani modovi:
  - queue  → odradi sve pending batch JSON-ove iz batch direktorija
  - batch  → odradi jedan konkretan batch JSON (korisno za debug)

Argumenti:
  - --path         → gdje na disku spremati glazbu (prosljeđuje se kao --base-path)
  - --dry-run      → ne skidaj ništa, samo proslijedi --dry-run na modules.download
  - --delete-done  → nakon uspješnog batcha obriši JSON umjesto da ga arhiviraš
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

try:
    # koristimo iste helper funkcije kao i postojeći download.py
    from config import get_downloader_batch_dir, get_default_music_root
except ImportError as exc:  # pragma: no cover - defensive
    print(
        "[FATAL] download_queue.py: ne mogu importati config helper funkcije:",
        exc,
        file=sys.stderr,
    )
    sys.exit(1)


log = logging.getLogger(__name__)


# =====================================================
#                    POMOĆNE FUNKCIJE
# =====================================================


def setup_logging(verbose: bool = True) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def resolve_music_root(path_arg: Optional[str]) -> Path:
    """Odredi root folder za skidanje glazbe.

    Prioritet:
      1) --path argument
      2) get_default_music_root() iz config.py
    """
    if path_arg:
        root = Path(path_arg).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return root

    mr = get_default_music_root()
    if mr is not None:
        mr = mr.expanduser()
        mr.mkdir(parents=True, exist_ok=True)
        return mr

    raise SystemExit(
        "Nije zadana putanja (--path), a get_default_music_root() vraća None."
    )


def get_batch_dir() -> Path:
    """Direktorij gdje se nalaze batch JSON-ovi (tasks-lista) za downloader."""
    p = Path(get_downloader_batch_dir())
    p.mkdir(parents=True, exist_ok=True)
    return p


def run_download_batch(json_path: Path, base_path: Path, dry_run: bool) -> int:
    """Pozovi postojeći modules.download za jedan batch JSON.

    Vraća exit code pod-procesa.
    """
    cmd: List[str] = [
        sys.executable,
        "-m",
        "modules.download",
        "batch",
        "--json",
        str(json_path),
        "--base-path",
        str(base_path),
        "--info",
    ]
    if dry_run:
        cmd.append("--dry-run")

    log.info("Pozivam: %s", " ".join(cmd))
    proc = subprocess.run(cmd)
    return proc.returncode


# =====================================================
#                    HANDLERS
# =====================================================


def handle_batch(args: argparse.Namespace) -> None:
    """Odradi JEDAN batch JSON (kroz existing modules.download)."""
    json_path = Path(args.json).expanduser()
    if not json_path.is_file():
        raise SystemExit(f"Ne postoji batch JSON: {json_path}")

    base_path = resolve_music_root(args.path)

    exit_code = run_download_batch(json_path, base_path, dry_run=args.dry_run)
    if exit_code == 0:
        log.info("Batch %s odrađen uspješno (exit=0).", json_path.name)
    else:
        log.error("Batch %s završio s greškom (exit=%d).", json_path.name, exit_code)


def handle_queue(args: argparse.Namespace) -> None:
    """Odradi SVE pending batch JSON-ove u batch direktoriju.

    "Pending" = svi *.json u batch direktoriju.

    - Svi batch-evi koji završe s exit=0:
        * u normalnom modu se presele u poddirektorij `done/`
        * ako je zadano --delete-done, JSON se obriše
    - Batch-evi s greškom ostaju gdje jesu (za kasniji retry).
    """
    batch_dir = get_batch_dir()
    base_path = resolve_music_root(args.path)

    done_dir = batch_dir / "done"
    done_dir.mkdir(parents=True, exist_ok=True)

    # pending = svi *.json u root batch_dir (ne diramo ono što je već u done/)
    json_files = sorted(p for p in batch_dir.glob("*.json"))

    if not json_files:
        log.info("Nema pending batch JSON-ova u %s.", batch_dir)
        return

    log.info("Našao %d batch JSON fajlova u queue-u (%s).", len(json_files), batch_dir)

    total_batches = len(json_files)
    ok_batches = 0
    err_batches = 0

    for idx, json_path in enumerate(json_files, start=1):
        log.info("[%d/%d] Batch: %s", idx, total_batches, json_path.name)
        exit_code = run_download_batch(json_path, base_path, dry_run=args.dry_run)

        if exit_code == 0:
            ok_batches += 1
            if args.dry_run:
                log.info(
                    "  [DRY-RUN] Batch %s bi bio označen kao gotov (premješten ili obrisan).",
                    json_path.name,
                )
            else:
                if args.delete_done:
                    json_path.unlink(missing_ok=True)
                    log.info("  Batch %s uspješan, JSON obrisan (--delete-done).", json_path.name)
                else:
                    target = done_dir / json_path.name
                    json_path.rename(target)
                    log.info(
                        "  Batch %s uspješan, premješten u %s.",
                        json_path.name,
                        target,
                    )
        else:
            err_batches += 1
            log.error(
                "  Batch %s završio s greškom (exit=%d). JSON ostaje u queue-u.",
                json_path.name,
                exit_code,
            )

    log.info(
        "QUEUE sažetak: %d OK batch(eva), %d batch(eva) s greškama, ukupno %d.",
        ok_batches,
        err_batches,
        total_batches,
    )


# =====================================================
#                    ARGPARSE / MAIN
# =====================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m modules.download_queue",
        description=(
            "Download queue modul za Z-Music Organizer.\n"
            "Radi nad batch JSON-ovima koje generiraju download_gen_* skripte "
            "i delegira stvarni download na modules.download."
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # batch
    p_batch = subparsers.add_parser(
        "batch", help="Odradi jedan batch JSON preko modules.download."
    )
    p_batch.add_argument(
        "--json",
        required=True,
        help="Putanja do batch JSON datoteke (sa 'tracks' listom).",
    )
    p_batch.add_argument(
        "--path",
        help=(
            "Root folder gdje se sprema muzika. Ako nije zadano, koristi se "
            "get_default_music_root() iz config.py."
        ),
    )
    p_batch.add_argument(
        "--dry-run",
        action="store_true",
        help="Ne skidaj ništa, samo proslijedi --dry-run na modules.download.",
    )
    p_batch.set_defaults(func=handle_batch)

    # queue
    p_queue = subparsers.add_parser(
        "queue", help="Odradi sve pending batch JSON-ove u batch direktoriju."
    )
    p_queue.add_argument(
        "--path",
        help=(
            "Root folder gdje se sprema muzika. Ako nije zadano, koristi se "
            "get_default_music_root() iz config.py."
        ),
    )
    p_queue.add_argument(
        "--dry-run",
        action="store_true",
        help="Ne skidaj ništa, samo proslijedi --dry-run na modules.download.",
    )
    p_queue.add_argument(
        "--delete-done",
        action="store_true",
        help=(
            "Ako je zadano, uspješno odrađeni batch JSON-ovi se brišu. "
            "Inače se premještaju u poddirektorij 'done/'."
        ),
    )
    p_queue.set_defaults(func=handle_queue)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    setup_logging(verbose=True)
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
