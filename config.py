#!/usr/bin/env python3
"""
config.py

Centralno mjesto za sve putanje i osnovne postavke Z-Music Organizer projekta.
"""

from pathlib import Path


# ---------------------------------------------------------------------------
# Projekt root
# ---------------------------------------------------------------------------

def get_project_root() -> Path:
    """
    Vraća root projekta (folder gdje se nalazi ovaj config.py).
    Pretpostavka: config.py je direktno u rootu git repozitorija.
    """
    return Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# SQLite baza
# ---------------------------------------------------------------------------

def get_database_dir() -> Path:
    """
    Vraća direktorij gdje se nalazi glavna SQLite baza.
    Default: <project_root>/database
    """
    return get_project_root() / "database"


def get_main_db_path() -> Path:
    """
    Vraća putanju do glavne SQLite baze.
    Default: <project_root>/database/tracks.db

    Ako direktorij ne postoji, kreira ga.
    """
    db_dir = get_database_dir()
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "tracks.db"
# ---------------------------------------------------------------------
# Hidden direktorij za interne JSON-ove (tokeni, cache, itd.)
# ---------------------------------------------------------------------

def get_hidden_dir() -> str:
    """
    Vraća putanju do skrivenog direktorija za interne JSON-ove.
    Primjer: /Users/khlm/ML/.hidden

    Ako direktorij ne postoji, kreira ga.
    """
    root = Path(get_project_root())
    hidden = root / ".hidden"
    hidden.mkdir(exist_ok=True)
    return str(hidden)


def get_hidden_json_path(filename: str) -> str:
    """
    Vraća full path do JSON fajla unutar .hidden direktorija.

    Primjer:
        get_hidden_json_path("spotify_oauth_token.json")
        -> /Users/khlm/ML/.hidden/spotify_oauth_token.json
    """
    return str(Path(get_hidden_dir()) / filename)


# ---------------------------------------------------------------------
# Alias za analysis DB (za analiziraj.py i ostale module)
# Trenutno koristimo istu bazu kao main (tracks.db).
# ---------------------------------------------------------------------

def get_analysis_db_path() -> str:
    """
    Putanja do baze koju koristi analiza (trenutno ista kao main DB).

    Ako kasnije razdvojimo na dvije baze, ovdje ćemo samo promijeniti path.
    """
    return get_main_db_path()