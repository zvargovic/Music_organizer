#!/usr/bin/env python3
"""
spotify_oauth.py

Jednostavan Spotify OAuth modul baziran na Spotipy.

CILJ:
- ZA TEBE i ZA KASNIJI UI: jedna glavna komanda koju korisnik pokrene.

Ponašanje:
- Ako NEMA credova (Client ID / Secret / Redirect URI):
    -> pita korisnika za unos (jednom),
       spremi u hidden JSON,
       nastavi dalje.
- Ako NEMA tokena:
    -> pokrene OAuth login (otvori browser),
       korisnik autorizira,
       token + refresh_token se spremaju u JSON.
- Ako IMA token:
    -> Spotipy ga automatski osvježi ako je istekao,
       provjerava current_user().

CLI:
    # Glavna pametna komanda (ovo ćeš koristiti 99% vremena):
    python -m modules.spotify_oauth

    # Dodatno, za debug:
    python -m modules.spotify_oauth info

Za ostale module:
    from modules.spotify_oauth import get_spotify_client
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler

from config import get_hidden_json_path


# ---------------------------------------------------------------------------
# Postavke & fajlovi
# ---------------------------------------------------------------------------

# Gdje se spremaju credovi i token, unutar "skrivenog" direktorija
CRED_FILENAME = "spotify_credentials.json"
TOKEN_CACHE_FILENAME = "spotify_oauth_token.json"

# Scope-ovi za cijeli sustav
SPOTIFY_SCOPES = [
    "user-read-email",
    "user-read-private",
    "user-library-read",
    "user-follow-read",
    "playlist-read-private",
    "playlist-modify-private",
    "playlist-modify-public",
]

DEFAULT_REDIRECT_URI = "http://127.0.0.1:9090/callback"


def _get_cred_path() -> str:
    path = get_hidden_json_path(CRED_FILENAME)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def _get_token_cache_path() -> str:
    path = get_hidden_json_path(TOKEN_CACHE_FILENAME)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Credovi (Client ID / Secret / Redirect URI)
# ---------------------------------------------------------------------------

def _load_credentials() -> Optional[Dict[str, str]]:
    """
    Pokuša učitati credove iz JSON-a.
    Ako ne postoje, fallback je env (za napredne korisnike).
    """
    cred_path = _get_cred_path()
    if os.path.isfile(cred_path):
        try:
            with open(cred_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cid = data.get("client_id") or data.get("SPOTIPY_CLIENT_ID")
            csec = data.get("client_secret") or data.get("SPOTIPY_CLIENT_SECRET")
            redir = data.get("redirect_uri") or data.get("SPOTIPY_REDIRECT_URI") or DEFAULT_REDIRECT_URI
            if cid and csec:
                return {
                    "client_id": cid,
                    "client_secret": csec,
                    "redirect_uri": redir,
                }
        except Exception:
            # pokvaren JSON -> tretiraj kao da ne postoji
            pass

    # fallback na env ako netko želi koristiti export
    cid = os.getenv("SPOTIPY_CLIENT_ID")
    csec = os.getenv("SPOTIPY_CLIENT_SECRET")
    redir = os.getenv("SPOTIPY_REDIRECT_URI") or DEFAULT_REDIRECT_URI
    if cid and csec:
        return {
            "client_id": cid,
            "client_secret": csec,
            "redirect_uri": redir,
        }

    return None


def _save_credentials(client_id: str, client_secret: str, redirect_uri: str) -> None:
    data = {
        "client_id": client_id.strip(),
        "client_secret": client_secret.strip(),
        "redirect_uri": redirect_uri.strip() or DEFAULT_REDIRECT_URI,
    }
    cred_path = _get_cred_path()
    with open(cred_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[OK] Spotify credovi spremljeni u: {cred_path}")


def _ensure_credentials(interactive: bool) -> Dict[str, str]:
    """
    Osigurava da imamo ispravne credove.

    Ako postoje u JSON-u (ili env), vrati dict i napuni os.environ.
    Ako ne postoje i interactive=True, pita korisnika i spremi.
    Ako ne postoje i interactive=False, ispiše error i izađe.
    """
    creds = _load_credentials()

    if not creds:
        if not interactive:
            print("[ERROR] Spotify credovi nisu konfigurirani.")
            print("Pokreni (jednom):")
            print("  python -m modules.spotify_oauth")
            sys.exit(1)

        # interactive = True -> pitaj korisnika
        print("=== Spotify API konfiguracija (prvo pokretanje) ===")
        print("Unesi podatke iz Spotify Developer Dashboarda.")
        print()

        client_id = input("Client ID: ").strip()
        client_secret = input("Client Secret: ").strip()
        redirect_uri = input(
            f"Redirect URI [{DEFAULT_REDIRECT_URI}]: "
        ).strip() or DEFAULT_REDIRECT_URI

        if not client_id or not client_secret:
            print("[ERROR] Client ID i Client Secret su obavezni.")
            sys.exit(1)

        _save_credentials(client_id, client_secret, redirect_uri)
        creds = {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }

    # napuni env varijable da ih Spotipy koristi standardno
    os.environ["SPOTIPY_CLIENT_ID"] = creds["client_id"]
    os.environ["SPOTIPY_CLIENT_SECRET"] = creds["client_secret"]
    os.environ["SPOTIPY_REDIRECT_URI"] = creds.get("redirect_uri", DEFAULT_REDIRECT_URI)

    return creds


# ---------------------------------------------------------------------------
# Public helperi za ostatak projekta
# ---------------------------------------------------------------------------

def get_auth_manager(scope: Optional[str] = None, interactive: bool = False) -> SpotifyOAuth:
    """
    Vrati SpotifyOAuth auth manager s našim cache handlerom.

    scope:
        Ako je None, koristi zadane SPOTIFY_SCOPES.
    interactive:
        Ako je True, može pokrenuti wizard za credove.
        Inače očekuje da su credovi već postavljeni.
    """
    _ensure_credentials(interactive=interactive)

    if scope is None:
        scope = " ".join(SPOTIFY_SCOPES)

    cache_path = _get_token_cache_path()
    cache_handler = CacheFileHandler(cache_path=cache_path)

    auth_manager = SpotifyOAuth(
        scope=scope,
        cache_handler=cache_handler,
        open_browser=True,   # na macOS-u će otvoriti default browser
        show_dialog=False,   # ne forsiraj ponovnu autorizaciju ako već postoji
    )
    return auth_manager


def get_spotify_client(scope: Optional[str] = None) -> spotipy.Spotify:
    """
    Vrati inicijalizirani spotipy.Spotify klijent s našim auth managerom.

    Za ostale module:
        sp = get_spotify_client()
    (ovdje ne ide interactive wizard; pretpostavlja se da je oauth već napravljen)
    """
    auth_manager = get_auth_manager(scope=scope, interactive=False)
    sp = spotipy.Spotify(auth_manager=auth_manager)
    return sp


# ---------------------------------------------------------------------------
# CLI: auto (default) + info
# ---------------------------------------------------------------------------

def _load_cached_token(auth_manager: SpotifyOAuth) -> Optional[Dict[str, Any]]:
    token_info = None
    try:
        token_info = auth_manager.cache_handler.get_cached_token()
    except Exception:
        token_info = None
    return token_info


def _format_remaining(expires_at_ts: Optional[int]) -> str:
    if expires_at_ts is None:
        return "nepoznato"
    now_ts = int(datetime.now().timestamp())
    delta = expires_at_ts - now_ts
    if delta <= 0:
        return "istekao"
    mins, sec = divmod(delta, 60)
    hrs, mins = divmod(mins, 60)
    days, hrs = divmod(hrs, 24)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hrs:
        parts.append(f"{hrs}h")
    if mins:
        parts.append(f"{mins}m")
    if sec and not parts:
        parts.append(f"{sec}s")
    return "za " + " ".join(parts)


def cmd_auto() -> None:
    """
    Glavna pametna komanda (bez argumenata):

    - Ako nema credova -> pita te, spremi ih.
    - Ako nema tokena -> pokrene OAuth login, spremi token.
    - Ako ima token -> Spotipy ga po potrebi osvježi.
    - Uvijek na kraju provjerava current_user().
    """
    print("=== Spotify OAuth (auto) ===")
    creds = _ensure_credentials(interactive=True)
    print(f"[INFO] Korišteni Spotify Client ID: {creds['client_id'][:8]}...")

    auth_manager = get_auth_manager(interactive=False)
    token_info = _load_cached_token(auth_manager)

    if not token_info:
        print("[INFO] Nema spremljenog tokena -> prvi login (otvaram browser).")
    else:
        expires_at_ts = token_info.get("expires_at")
        if expires_at_ts is not None:
            expires_at = datetime.fromtimestamp(expires_at_ts).isoformat(
                sep=" ", timespec="seconds"
            )
        else:
            expires_at = "nepoznato"
        remaining = _format_remaining(expires_at_ts)
        print(f"[INFO] Postojeći token, expires_at: {expires_at} ({remaining})")
        print("[INFO] Ako je istekao, Spotipy će ga automatski osvježiti.")

    sp = spotipy.Spotify(auth_manager=auth_manager)

    try:
        me = sp.current_user()
    except Exception as exc:
        print("[ERROR] Neuspješan login/refresh ili dohvat korisnika.")
        print(f"Detalji: {exc}")
        sys.exit(1)

    print()
    print("[OK] Spotify OAuth je spreman.")
    print("Prijavljeni korisnik:")
    print(f"  display_name : {me.get('display_name')}")
    print(f"  id           : {me.get('id')}")
    print(f"  email        : {me.get('email')}")
    print(f"  product      : {me.get('product')}")
    print()
    print(f"Cred file : {_get_cred_path()}")
    print(f"Token file: {_get_token_cache_path()}")


def cmd_info() -> None:
    """
    Debug info:
    - putanje cred/token fileova
    - sadržaj tokena (token_info dict)
    - expires_at u human readable formatu
    - current_user()
    """
    # ovdje ne želimo da usput otvaramo browser, pa interactive=False
    auth_manager = get_auth_manager(interactive=False)
    token_info = _load_cached_token(auth_manager)

    cache_path = _get_token_cache_path()
    cred_path = _get_cred_path()
    print("=== Spotify OAuth info ===")
    print(f"Cred file : {cred_path}")
    print(f"Token file: {cache_path}")
    print()

    if not token_info:
        print("Status: NEMA spremljenog tokena.")
        print("Pokreni bez argumenata:")
        print("  python -m modules.spotify_oauth")
        return

    expires_at_ts = token_info.get("expires_at")
    if expires_at_ts is not None:
        expires_at = datetime.fromtimestamp(expires_at_ts).isoformat(
            sep=" ", timespec="seconds"
        )
    else:
        expires_at = "nepoznato"
    remaining = _format_remaining(expires_at_ts)

    print("Token info (raw dict):")
    print(json.dumps(token_info, indent=2, ensure_ascii=False))
    print()
    print("Token meta:")
    print(f"  expires_at       : {expires_at}")
    print(f"  remaining        : {remaining}")
    print(f"  has_refresh_token: {'DA' if token_info.get('refresh_token') else 'NE'}")
    print()

    sp = spotipy.Spotify(auth_manager=auth_manager)
    try:
        me = sp.current_user()
    except Exception as exc:
        print("[WARN] Ne mogu dohvatiti current_user() s ovim tokenom.")
        print(f"Detalji: {exc}")
        return

    print("Current user (provjera tokena):")
    print(f"  display_name : {me.get('display_name')}")
    print(f"  id           : {me.get('id')}")
    print(f"  email        : {me.get('email')}")
    print(f"  product      : {me.get('product')}")


# ---------------------------------------------------------------------------
# CLI ulazna točka
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m modules.spotify_oauth",
        description="Spotify OAuth helper modul (auto / info).",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["info"],
        help="Ako se ne navede, pokreće se 'auto' wizard.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        cmd_auto()
    elif args.command == "info":
        cmd_info()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
