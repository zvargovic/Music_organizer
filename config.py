"""
Global configuration for Z-Music Organizer.

Ovaj config.py sadrži sve funkcije koje moduli trenutačno očekuju:
- get_main_db_path            → modules.load
- get_spotify_credentials_path → modules.spotify_oauth, modules.match
- get_spotify_token_path      → modules.spotify_oauth
- get_match_log_dir           → modules.match
- get_hidden_json_path        → modules.spotify_oauth (i po potrebi drugi)
"""

from __future__ import annotations

from pathlib import Path
import os
from typing import Optional

# -------------------------------------------------------------------------
# OSNOVNE PUTANJE
# -------------------------------------------------------------------------

# Root projekta (gdje je ovaj config.py)
PROJECT_ROOT = Path(__file__).resolve().parent

# Baza ide u PROJECT_ROOT/database/tracks.db
DATABASE_DIR = PROJECT_ROOT / "database"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
MAIN_DB_PATH = DATABASE_DIR / "tracks.db"


def get_main_db_path() -> Path:
    """
    Vrati apsolutni path do glavne SQLite baze.
    load.py očekuje Path objekt, ne string.
    """
    return MAIN_DB_PATH


# -------------------------------------------------------------------------
# SPOTIFY CONFIG (credentials + token)
# -------------------------------------------------------------------------

def get_spotify_credentials_path() -> str:
    """
    Vraća istu putanju koju spotify_oauth već koristi
    za cred file (hidden dot fajl u rootu).

    Koriste:
    - modules.spotify_oauth (posredno preko get_hidden_json_path)
    - modules.match.build_spotify_client()
    """
    return get_hidden_json_path("spotify_credentials.json")


def get_spotify_token_path() -> str:
    """
    Vraća istu putanju koju spotify_oauth koristi
    za token file (hidden dot fajl u rootu).
    """
    return get_hidden_json_path("spotify_oauth_token.json")



# -------------------------------------------------------------------------
# MATCH LOGOVI
# -------------------------------------------------------------------------

MATCH_LOG_DIR = PROJECT_ROOT / "logs" / "match"


def get_match_log_dir() -> str:
    """
    Vrati folder za match logove. Ako ne postoji, kreira ga.

    Koristi:
    - modules.match.setup_logging()
    """
    MATCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return str(MATCH_LOG_DIR)


# -------------------------------------------------------------------------
# POMOĆNI HELPER ZA SKRIVENE JSON FAJLOVE
# -------------------------------------------------------------------------

def get_hidden_json_path(filename: str) -> str:
    """
    Helper za 'skrivene' (dot) JSON fajlove koje koristi spotify_oauth.py.

    spotify_oauth zove:
        get_hidden_json_path(CRED_FILENAME)

    CRED_FILENAME je samo ime fajla (npr. 'spotify_credentials.json'),
    a mi ga mapiramo na:

        PROJECT_ROOT/.spotify_credentials.json
    """
    # spremamo u root projekta kao dot-fajl
    name = filename
    if not name.startswith("."):
        name = "." + name
    return str(PROJECT_ROOT / name)
# -------------------------------------------------------------------------
# Downloader helperi
# -------------------------------------------------------------------------

def get_downloader_log_dir() -> str:
    """
    Folder za downloader logove.

    Primjer: <PROJECT_ROOT>/logs/download

    Kreira direktorij ako ne postoji i vraća ga kao string.
    """
    log_dir = PROJECT_ROOT / "logs" / "download"
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir)


def get_downloader_tmp_dir() -> str:
    """
    Privremeni folder koji downloader može koristiti za pomoćne fajlove.

    Primjer: <PROJECT_ROOT>/tmp/download

    Kreira direktorij ako ne postoji i vraća ga kao string.
    """
    tmp_dir = PROJECT_ROOT / "tmp" / "download"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return str(tmp_dir)


def get_downloader_batch_dir() -> str:
    """
    Folder gdje se čuvaju batch JSON liste za downloader.

    Primjer: <PROJECT_ROOT>/data/download_batches

    Kreira direktorij ako ne postoji i vraća ga kao string.
    """
    batch_dir = PROJECT_ROOT / "data" / "download_batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    return str(batch_dir)


def get_default_music_root() -> Optional[Path]:
    """
    Opcionalni default MUSIC_ROOT za skripte (npr. downloader) koje rade nad
    cijelom kolekcijom.

    Ako je postavljena env varijabla ZMUSIC_MUSIC_ROOT, vraća Path na tu
    lokaciju. Inače vraća None i skripte trebaju zahtijevati --base-path.
    """
    env = os.environ.get("ZMUSIC_MUSIC_ROOT")
    if not env:
        return None
    return Path(env).expanduser()