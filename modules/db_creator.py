#!/usr/bin/env python3
"""
db_creator.py

Modul za upravljanje SQLite bazom Z-Music Organizera:

  - create : kreira novu bazu (tracks.db) prema shemi
  - info   : ispisuje osnovne info/statuse baze
  - drop   : briše *datoteku* baze
  - clear  : briše sve zapise iz tablice tracks, ali ostavlja strukturu baze

Default lokacija baze:
  <project_root>/database/tracks.db
  (preko config.get_main_db_path)
"""

import argparse
import sqlite3
from pathlib import Path
from datetime import datetime

from config import get_main_db_path


# ---------------------------------------------------------------------------
# SQL shema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

/* Verzija sheme baze */
PRAGMA user_version = 1;

/* Glavna tablica: tracks
   Jedan zapis = jedna lokalna audio datoteka
*/
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identitet lokalnog filea
    file_path          TEXT NOT NULL UNIQUE,  -- apsolutna ili canonical putanja
    file_hash          TEXT NOT NULL UNIQUE,  -- stabilni hash sadržaja (npr. SHA256)
    file_size          INTEGER,              -- veličina u bajtovima
    mtime              REAL,                 -- modification time (Unix timestamp)

    added_at           TEXT NOT NULL,        -- ISO8601 (kad je prvi put ušla u bazu)
    updated_at         TEXT NOT NULL,        -- ISO8601 (zadnja obrada / refresh)

    -- Osnovni tagovi (lokalni ili iz Spotifya)
    title              TEXT,
    artist             TEXT,
    album              TEXT,
    album_artist       TEXT,
    track_number       INTEGER,
    disc_number        INTEGER,
    year               INTEGER,
    genre              TEXT,
    duration_sec       REAL,

    -- Spotify meta (iz meta_s JSON-a)
    spotify_id         TEXT,
    spotify_url        TEXT,
    spotify_preview_url TEXT,
    spotify_popularity INTEGER,
    spotify_isrc       TEXT,
    spotify_album_id   TEXT,
    spotify_artist_ids TEXT,     -- npr. JSON lista ili comma-separated
    spotify_match_score REAL,    -- 0.0–1.0

    -- Sažetak audio analize (iz audio/final JSON-a)
    bpm                REAL,
    key                TEXT,     -- npr. "C", "F#", ...
    key_scale          TEXT,     -- "major" / "minor"
    loudness_db        REAL,
    danceability       REAL,
    energy             REAL,
    valence            REAL,
    acousticness       REAL,
    instrumentalness   REAL,
    tempo_confidence   REAL,

    -- Putevi do JSON datoteka
    meta_s_path        TEXT,     -- json/meta_s/...
    audio_path         TEXT,     -- json/audio/...
    final_path         TEXT,     -- json/final/...

    -- Verzije / flagovi
    analysis_version       INTEGER,  -- verzija analize (dogovorena u configu)
    spotify_meta_version   INTEGER,  -- verzija Spotify meta sloja

    is_missing         INTEGER DEFAULT 0,  -- file više ne postoji na disku
    is_duplicate       INTEGER DEFAULT 0,  -- označen kao duplikat
    notes              TEXT               -- slobodan tekst / debug
);

/* Indexi za najčešće upite */
CREATE INDEX IF NOT EXISTS idx_tracks_file_hash
    ON tracks(file_hash);

CREATE INDEX IF NOT EXISTS idx_tracks_spotify_id
    ON tracks(spotify_id);

CREATE INDEX IF NOT EXISTS idx_tracks_artist_title
    ON tracks(artist, title);

CREATE INDEX IF NOT EXISTS idx_tracks_year
    ON tracks(year);
"""


# ---------------------------------------------------------------------------
# Helperi
# ---------------------------------------------------------------------------

def get_db_path(custom: str | None) -> Path:
    """
    Ako je zadana custom putanja, koristi nju.
    Inače koristi default iz config.get_main_db_path().
    """
    if custom:
        p = Path(custom).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return get_main_db_path()


def _human_size(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "n/a"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for u in units:
        if size < 1024.0:
            return f"{size:.1f} {u}"
        size /= 1024.0
    return f"{size:.1f} PB"


# ---------------------------------------------------------------------------
# Operacije
# ---------------------------------------------------------------------------

def op_create(db_path: Path, force: bool = False) -> None:
    """
    Kreira novu bazu na zadanoj lokaciji.
    Ako datoteka postoji i force=False -> error.
    Ako force=True -> briše staru datoteku pa kreira novu.
    """
    if db_path.exists() and not force:
        raise SystemExit(
            f"[ERROR] Baza već postoji: {db_path}\n"
            f"        Ako je želiš prebrisati, pokreni: create --force"
        )

    if db_path.exists() and force:
        db_path.unlink()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()

    print(f"[OK] Kreirana baza: {db_path}")
    print("[OK] Tablica 'tracks' je spremna.")


def op_drop(db_path: Path, yes: bool = False) -> None:
    """
    Briše *datoteku* baze.
    """
    if not db_path.exists():
        print(f"[INFO] Baza ne postoji: {db_path}")
        return

    if not yes:
        ans = input(
            f"⚠  Sigurno želiš OBRISATI datoteku baze?\n"
            f"   Path: {db_path}\n"
            f"   Upisi 'yes' za potvrdu: "
        ).strip().lower()
        if ans != "yes":
            print("[INFO] Odustajem od brisanja baze.")
            return

    db_path.unlink()
    print(f"[OK] Datoteka baze obrisana: {db_path}")


def op_clear(db_path: Path, yes: bool = False) -> None:
    """
    Briše SVE zapise iz tablice tracks, ali ostavlja shemu/bazu.
    """
    if not db_path.exists():
        print(f"[INFO] Baza ne postoji: {db_path}")
        return

    if not yes:
        ans = input(
            "⚠  CLEAR će obrisati SVE redove iz tablice 'tracks',\n"
            "   ali će ostaviti strukturu baze.\n"
            "   Upisi 'clear' za potvrdu: "
        ).strip().lower()
        if ans != "clear":
            print("[INFO] Odustajem od clear operacije.")
            return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tracks;")
        conn.commit()
        cur.execute("VACUUM;")
        conn.commit()
    except sqlite3.OperationalError as e:
        print("[ERROR] SQLite greška pri CLEAR operaciji:")
        print(f"       {e}")
        print("       Možda tablica 'tracks' još ne postoji?")
        return
    finally:
        conn.close()

    print(f"[OK] Tablica 'tracks' je očišćena u bazi: {db_path}")


def op_info(db_path: Path) -> None:
    """
    Ispisuje osnovne info o bazi i statistikama iz tracks.
    """
    if not db_path.exists():
        print(f"[INFO] Baza ne postoji: {db_path}")
        return

    stat = db_path.stat()
    size_str = _human_size(stat.st_size)
    # ispravno polje je st_mtime, ne mtime
    mtime = datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds")

    print("=== Osnovne informacije o bazi ===")
    print(f"Path:            {db_path}")
    print(f"Veličina:        {size_str}")
    print(f"Zadnja izmjena:  {mtime}")
    print("")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        # user_version
        cur.execute("PRAGMA user_version;")
        row = cur.fetchone()
        user_version = row[0] if row else 0

        # track statistika
        cur.execute(
            "SELECT COUNT(*) AS n_tracks, "
            "MIN(added_at) AS first_added, "
            "MAX(added_at) AS last_added "
            "FROM tracks;"
        )
        stats = cur.fetchone()

        # broj različitih artista
        cur.execute("SELECT COUNT(DISTINCT artist) FROM tracks WHERE artist IS NOT NULL;")
        n_artists = cur.fetchone()[0]

        # broj zapisa s Spotify ID-om
        cur.execute("SELECT COUNT(*) FROM tracks WHERE spotify_id IS NOT NULL;")
        n_spotify = cur.fetchone()[0]

    except sqlite3.OperationalError as e:
        print("[ERROR] Problem pri čitanju iz baze.")
        print(f"SQLite error: {e}")
        print("Možda tablica 'tracks' još ne postoji ili je baza oštećena.")
        return
    finally:
        conn.close()

    print("=== SQLite PRAGMA ===")
    print(f"user_version:    {user_version}")
    print("")
    print("=== Statistika tablice 'tracks' ===")
    print(f"Ukupno zapisa:         {stats['n_tracks'] if stats else 'n/a'}")
    print(f"Različitih artista:    {n_artists}")
    print(f"Zapisa sa Spotify ID:  {n_spotify}")
    if stats:
        print(f"Prvi added_at:         {stats['first_added']}")
        print(f"Zadnji added_at:       {stats['last_added']}")
    print("")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Z-Music Organizer — DB Creator (create / info / drop / clear)",
    )

    parser.add_argument(
        "command",
        choices=["create", "info", "drop", "clear"],
        help="akcija koju želiš: create | info | drop | clear",
    )

    parser.add_argument(
        "--db",
        dest="db_path",
        type=str,
        default=None,
        help="custom putanja do baze (default: iz config.get_main_db_path)",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="kod 'create': ako postoji stara baza, obriši je i kreiraj novu",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="kod 'drop' i 'clear': ne traži interaktivnu potvrdu",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = get_db_path(args.db_path)

    if args.command == "create":
        op_create(db_path, force=args.force)
    elif args.command == "info":
        op_info(db_path)
    elif args.command == "drop":
        op_drop(db_path, yes=args.yes)
    elif args.command == "clear":
        op_clear(db_path, yes=args.yes)
    else:
        raise SystemExit("Nepoznata komanda (ovo se ne bi smjelo dogoditi).")


if __name__ == "__main__":
    main()
