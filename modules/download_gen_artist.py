"""Download batch generator: artist collection / album / track.

Ovaj modul NE skida audio, nego samo generira batch JSON datoteke
za downloader modul (`modules.download`).

Mode-ovi:
  collection  — svi albumi od artista
  album       — jedan album od artista
  track       — jedna pjesma od artista
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests

# Pretpostavka: postoji modules.config s putanjama
try:
    from modules import config
except ImportError:
    config = None

log = logging.getLogger(__name__)

SPOTIFY_API_BASE = "https://api.spotify.com/v1"


# =====================================================
#                    MODELI
# =====================================================


@dataclass
class TrackTask:
    """Jedan download task u batch JSON-u."""

    spotify_id: str
    artist: str
    album: str
    year: int
    title: str

    def to_json(self) -> Dict[str, Any]:
        return {
            "type": "track",
            "spotify_id": self.spotify_id,
            "artist": self.artist,
            "album": self.album,
            "year": self.year,
            "title": self.title,
        }


# =====================================================
#                    POMOĆNE FUNKCIJE
# =====================================================


def setup_logging(verbose: bool = True) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def get_default_batch_dir() -> Path:
    """Vrati default batch direktorij iz configa ili lokalni fallback."""

    if config is not None and hasattr(config, "DOWNLOAD_BATCH_DIR"):
        return Path(config.DOWNLOAD_BATCH_DIR)
    return Path("data/download_batches")


def resolve_output_path(out_arg: Optional[str], suffix: str) -> Path:
    if out_arg:
        return Path(out_arg)

    batch_dir = get_default_batch_dir()
    batch_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return batch_dir / f"{suffix}_{ts}.json"


def write_batch(tasks: List[TrackTask], out_path: Path, info: bool = False) -> None:
    data = {"tasks": [t.to_json() for t in tasks]}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    if info:
        log.info("Zapisao batch JSON: %s", out_path)
        log.info("Broj taskova: %d", len(tasks))


# ---------- Spotify token / HTTP ----------


def _resolve_token_path() -> Path:
    """Pokušaj pronaći Spotify token JSON na više mogućih lokacija."""
    # 1) eksplicitno iz configa, ako postoji
    if config is not None:
        for attr in ("SPOTIFY_TOKEN_PATH", "SPOTIFY_TOKEN_FILE", "SPOTIFY_TOKEN_JSON"):
            if hasattr(config, attr):
                p = Path(getattr(config, attr))
                if p.is_file():
                    return p

        # 2) ako postoji DATA_DIR, probaj unutar njega
        if hasattr(config, "DATA_DIR"):
            data_dir = Path(getattr(config, "DATA_DIR"))
            for cand in ("spotify_token.json", "spotify/token.json"):
                p = data_dir / cand
                if p.is_file():
                    return p

    # 3) fallback relativno na projekt
    for cand in (
        Path("data/spotify/token.json"),
        Path("data/spotify_token.json"),
    ):
        if cand.is_file():
            return cand

    # ako još uvijek nismo našli, vratimo default (možda ne postoji)
    return Path("data/spotify/token.json")


def load_spotify_token() -> Dict[str, Any]:
    token_path = _resolve_token_path()
    if not token_path.is_file():
        raise SystemExit(
            f"Nisam našao Spotify token JSON. Pokreni prvo spotify_oauth.py.\n"
            f"Traženi path: {token_path}"
        )

    with token_path.open("r", encoding="utf-8") as f:
        token = json.load(f)

    if "access_token" not in token:
        raise SystemExit(f"Spotify token JSON nema 'access_token' ključ: {token_path}")
    return token


def spotify_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    token = load_spotify_token()
    headers = {
        "Authorization": f"Bearer {token['access_token']}",
    }
    url = f"{SPOTIFY_API_BASE}{path}"
    resp = requests.get(url, headers=headers, params=params or {}, timeout=15)

    if resp.status_code == 401:
        raise SystemExit(
            "Spotify token je vjerojatno istekao (401). Pokreni ponovno spotify_oauth.py."
        )
    if resp.status_code >= 400:
        raise SystemExit(
            f"Spotify API error {resp.status_code}: {resp.text[:200]}"
        )

    return resp.json()


# ---------- Spotify helperi ----------


def search_artist_by_name(name: str) -> Dict[str, Any]:
    data = spotify_get(
        "/search",
        params={"q": name, "type": "artist", "limit": 5},
    )
    items = data.get("artists", {}).get("items", [])
    if not items:
        raise SystemExit(f"Nisam našao nijednog artista za ime: {name!r}")
    artist = items[0]
    log.info(
        "Artist match: %s (ID=%s)",
        artist.get("name"),
        artist.get("id"),
    )
    return artist


def get_artist_id(artist: Optional[str], artist_id: Optional[str]) -> str:
    if artist_id:
        return artist_id
    if not artist:
        raise SystemExit("Potrebno je zadati --artist ili --artist-id.")
    return search_artist_by_name(artist).get("id")


def get_artist_albums(artist_id: str, include_singles: bool) -> List[Dict[str, Any]]:
    include_groups = "album,single" if include_singles else "album"
    albums: Dict[str, Dict[str, Any]] = {}
    params = {
        "include_groups": include_groups,
        "limit": 50,
    }
    url_path = f"/artists/{artist_id}/albums"

    # jednostavna implementacija: jedna stranica (50) je najčešće dosta,
    # ako bude trebalo, kasnije ćemo dodati full paging
    data = spotify_get(url_path, params=params)
    for item in data.get("items", []):
        alb_id = item.get("id")
        if not alb_id:
            continue
        albums[alb_id] = item

    result = list(albums.values())
    log.info("Našao %d albuma za artist_id=%s", len(result), artist_id)
    return result


def parse_year(release_date: str) -> int:
    if not release_date:
        return 0
    try:
        return int(release_date[:4])
    except Exception:
        return 0


def get_album_tracks(album_id: str) -> Dict[str, Any]:
    """Vrati full album JSON (uklj. tracks) za zadani album ID."""
    data = spotify_get(f"/albums/{album_id}")
    return data


def build_tasks_for_album(album_data: Dict[str, Any]) -> List[TrackTask]:
    album_name = album_data.get("name", "")
    release_date = album_data.get("release_date", "")
    year = parse_year(release_date)

    artists = album_data.get("artists", []) or []
    if artists:
        album_artist_name = artists[0].get("name", "")
    else:
        album_artist_name = ""

    tracks = album_data.get("tracks", {}).get("items", [])
    tasks: List[TrackTask] = []
    for t in tracks:
        track_id = t.get("id")
        title = t.get("name", "")
        if not track_id or not title:
            continue
        tasks.append(
            TrackTask(
                spotify_id=track_id,
                artist=album_artist_name,
                album=album_name,
                year=year,
                title=title,
            )
        )
    log.info(
        "Album '%s' (%d) -> %d trackova",
        album_name,
        year,
        len(tasks),
    )
    return tasks


def choose_album_by_name(
    albums: List[Dict[str, Any]], album_name: str
) -> Dict[str, Any]:
    """Izaberi jedan album po imenu (case-insensitive).

    Ako ima više match-eva (deluxe/remaster), uzmi onaj s najnovijim release_date.
    """
    album_name_norm = album_name.strip().lower()
    candidates: List[Dict[str, Any]] = []
    for a in albums:
        name = (a.get("name") or "").strip().lower()
        if name == album_name_norm:
            candidates.append(a)

    if not candidates:
        # fallback: partial match
        for a in albums:
            name = (a.get("name") or "").strip().lower()
            if album_name_norm in name:
                candidates.append(a)

    if not candidates:
        raise SystemExit(
            f"Nisam našao album '{album_name}' među {len(albums)} albuma artista."
        )

    if len(candidates) == 1:
        chosen = candidates[0]
    else:
        # odaberi po najnovijoj godini
        chosen = max(
            candidates,
            key=lambda a: parse_year(a.get("release_date", "")),
        )
        log.info(
            "Više match-eva za album '%s' -> biram najnoviji: %s (%s)",
            album_name,
            chosen.get("name"),
            chosen.get("release_date"),
        )

    return chosen


def resolve_track_by_search(artist: str, track: str) -> Dict[str, Any]:
    query = f"track:{track} artist:{artist}"
    data = spotify_get(
        "/search",
        params={"q": query, "type": "track", "limit": 5},
    )
    items = data.get("tracks", {}).get("items", [])
    if not items:
        raise SystemExit(f"Nisam našao track '{track}' za artista '{artist}'.")
    chosen = items[0]
    log.info(
        "Track match: %s — %s (ID=%s)",
        chosen.get("artists", [{}])[0].get("name"),
        chosen.get("name"),
        chosen.get("id"),
    )
    return chosen


# =====================================================
#                    HANDLERS
# =====================================================


def handle_collection(args: argparse.Namespace) -> None:
    """Generate batch za SVE albume jednog artista."""

    artist_id = get_artist_id(args.artist, args.artist_id)
    albums = get_artist_albums(artist_id, include_singles=args.include_singles)

    tasks: List[TrackTask] = []
    for alb in albums:
        alb_id = alb.get("id")
        if not alb_id:
            continue
        # Dohvati full album s trackovima
        album_data = get_album_tracks(alb_id)
        tasks.extend(build_tasks_for_album(album_data))

    out_path = resolve_output_path(args.out, "artist_collection")
    write_batch(tasks, out_path, info=args.info)


def handle_album(args: argparse.Namespace) -> None:
    """Generate batch za JEDAN album."""

    if not args.album_id and not (args.artist or args.artist_id) and not args.album:
        raise SystemExit(
            "Za 'album' mod zadati ili --album-id ili kombinaciju "
            "--artist/--artist-id + --album."
        )

    if args.album_id:
        album_data = get_album_tracks(args.album_id)
    else:
        artist_id = get_artist_id(args.artist, args.artist_id)
        albums = get_artist_albums(artist_id, include_singles=True)
        chosen_meta = choose_album_by_name(albums, args.album)
        album_id = chosen_meta.get("id")
        if not album_id:
            raise SystemExit("Izabrani album nema ID.")
        album_data = get_album_tracks(album_id)

    tasks = build_tasks_for_album(album_data)

    out_path = resolve_output_path(args.out, "artist_album")
    write_batch(tasks, out_path, info=args.info)


def handle_track(args: argparse.Namespace) -> None:
    """Generate batch za JEDAN track."""

    if not args.track_id and not (args.artist or args.artist_id) and not args.track:
        raise SystemExit(
            "Za 'track' mod zadati ili --track-id ili kombinaciju "
            "--artist/--artist-id + --track."
        )

    if args.track_id:
        track_data = spotify_get(f"/tracks/{args.track_id}")
    else:
        # koristimo artist ime za search; ako je zadano samo artist_id,
        # moramo resolve-ati ime artista
        artist_name = args.artist
        if not artist_name and args.artist_id:
            artist_data = spotify_get(f"/artists/{args.artist_id}")
            artist_name = artist_data.get("name")

        if not artist_name:
            raise SystemExit("Za track search potrebno je ime artista (--artist).")

        track_data = resolve_track_by_search(artist_name, args.track)

    album = track_data.get("album", {}) or {}
    album_name = album.get("name", "")
    release_date = album.get("release_date", "")
    year = parse_year(release_date)

    artists = track_data.get("artists", []) or []
    if artists:
        artist_name = artists[0].get("name", "")
    else:
        artist_name = ""

    track_id = track_data.get("id")
    title = track_data.get("name", "")

    tasks: List[TrackTask] = []
    if track_id and title:
        tasks.append(
            TrackTask(
                spotify_id=track_id,
                artist=artist_name,
                album=album_name,
                year=year,
                title=title,
            )
        )
    else:
        raise SystemExit("Dobiveni track nema ID ili naziv.")

    out_path = resolve_output_path(args.out, "artist_track")
    write_batch(tasks, out_path, info=args.info)


# =====================================================
#                    ARGPARSE
# =====================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m modules.download_gen_artist",
        description=(
            "Generator download batch JSON datoteka za downloader.\n"
            "Mode: collection / album / track."
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # collection
    p_coll = subparsers.add_parser("collection", help="Svi albumi artista.")
    p_coll.add_argument("--artist", type=str, help="Ime artista (Spotify search).")
    p_coll.add_argument("--artist-id", type=str, help="Spotify artist ID.")
    p_coll.add_argument(
        "--include-singles",
        action="store_true",
        help="Uključi i singlove (release type 'single').",
    )
    p_coll.add_argument("--out", type=str, help="Putanja do output batch JSON-a.")
    p_coll.add_argument("--info", action="store_true", help="Ispiši sažetak.")
    p_coll.set_defaults(func=handle_collection)

    # album
    p_album = subparsers.add_parser("album", help="Jedan album artista.")
    p_album.add_argument("--artist", type=str, help="Ime artista (Spotify search).")
    p_album.add_argument("--artist-id", type=str, help="Spotify artist ID.")
    p_album.add_argument("--album", type=str, help="Naziv albuma.")
    p_album.add_argument("--album-id", type=str, help="Spotify album ID.")
    p_album.add_argument("--out", type=str, help="Putanja do output batch JSON-a.")
    p_album.add_argument("--info", action="store_true", help="Ispiši sažetak.")
    p_album.set_defaults(func=handle_album)

    # track
    p_track = subparsers.add_parser("track", help="Jedna pjesma artista.")
    p_track.add_argument("--artist", type=str, help="Ime artista (Spotify search).")
    p_track.add_argument("--artist-id", type=str, help="Spotify artist ID.")
    p_track.add_argument("--track", type=str, help="Naziv pjesme.")
    p_track.add_argument("--track-id", type=str, help="Spotify track ID.")
    p_track.add_argument("--out", type=str, help="Putanja do output batch JSON-a.")
    p_track.add_argument("--info", action="store_true", help="Ispiši sažetak.")
    p_track.set_defaults(func=handle_track)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
