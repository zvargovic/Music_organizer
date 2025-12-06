#!/usr/bin/env python3
"""match.py — per-track Spotify lookup

Zadatak:
- za jednu audio datoteku (zadanu preko --path) pročitati osnovne tagove,
  pronaći najbolji Spotify match preko Web API-ja,
  izračunati match_score,
  i zapisati skriveni JSON `.stem.spotify.json` uz audio datoteku.

Korištenje:
  python -m modules.match --path "/full/path/to/Track.flac"

Opcije:
  --dry-run   : ne zapisuje JSON, samo ispisuje rezultat
  --verbose   : detaljniji log (DEBUG)

Oslanja se na:
  - config.py (putanje za .hidden/ i logs/)
  - spotify_oauth.py (za inicijalni OAuth i spremanje credova)
  - biblioteku `spotipy` za Spotify Web API
  - biblioteku `mutagen` za čitanje audio tagova
"""

import argparse
import json
import logging
import sys
import unicodedata
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from utils.file_id import compute_file_hash

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
except ImportError as e:
    raise SystemExit(
        "ERROR: modul 'spotipy' nije instaliran. Dodaj ga u requirements i instaliraj."
    ) from e

try:
    from mutagen import File as MutagenFile
except ImportError as e:
    raise SystemExit(
        "ERROR: modul 'mutagen' nije instaliran. Dodaj ga u requirements i instaliraj."
    ) from e


# ---------------------------------------------------------------------------
# Spotify scope i client helper
# ---------------------------------------------------------------------------

SCOPE = (
    "user-read-email "
    "user-read-private "
    "user-library-read "
    "user-follow-read "
    "playlist-read-private "
    "playlist-modify-private "
    "playlist-modify-public"
)


def build_spotify_client() -> "spotipy.Spotify":
    """Stvara Spotipy client koristeći iste credential i token fileove
    koje koristi spotify_oauth modul.
    """
    cred_path = Path(config.get_spotify_credentials_path())
    token_path = Path(config.get_spotify_token_path())

    if not cred_path.exists():
        raise SystemExit(
            f"ERROR: Nema Spotify credova ({cred_path}).\n"
            f"Prvo pokreni: python -m modules.spotify_oauth"
        )

    with cred_path.open("r", encoding="utf-8") as f:
        cred = json.load(f)

    cid = cred.get("client_id")
    csecret = cred.get("client_secret")
    redirect_uri = cred.get("redirect_uri")

    if not cid or not csecret or not redirect_uri:
        raise SystemExit(
            "ERROR: Spotify credovi su nepotpuni (client_id/secret/redirect_uri).\n"
            "Pokreni ponovno spotify_oauth modul."
        )

    auth_manager = SpotifyOAuth(
        client_id=cid,
        client_secret=csecret,
        redirect_uri=redirect_uri,
        scope=SCOPE,
        cache_path=str(token_path),
        open_browser=True,
    )

    sp = spotipy.Spotify(auth_manager=auth_manager)
    # Lagana provjera da token radi
    me = sp.current_user()
    logging.info(
        "Spotify client spreman. Prijavljeni user: %s (%s)",
        me.get("display_name") or me.get("id"),
        me.get("email"),
    )
    return sp


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_logging(verbose: bool = False) -> None:
    log_dir = Path(config.get_match_log_dir())
    log_file = log_dir / "match.log"
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"

    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.debug("Logging initialized. Log file: %s", log_file)


# ---------------------------------------------------------------------------
# Modeli i utility funkcije
# ---------------------------------------------------------------------------


@dataclass
class LocalTags:
    artist: Optional[str]
    album: Optional[str]
    title: Optional[str]
    year: Optional[int]
    duration_sec: Optional[float]
    track_no: Optional[int]


@dataclass
class SpotifyTrackMeta:
    spotify_id: str
    spotify_url: str
    name: str
    artists: List[str]
    album_name: str
    album_id: str
    album_url: str
    release_date: str
    duration_ms: int
    disc_number: int
    track_number: int
    explicit: bool
    popularity: int
    isrc: Optional[str]
    match_score_raw: float
    match_score_percent: float
    search_query: str


def _normalize(s: str) -> str:
    """Lowercase, uklanja naglaske i višestruke razmake (za usporedbu)."""
    if not s:
        return ""
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = " ".join(s.split())
    return s


MAX_SCORE = 7.0  # teorijski max iz heuristike scoringa


def _score_to_percent(score: float) -> float:
    if score <= 0:
        return 0.0
    p = (score / MAX_SCORE) * 100.0
    if p > 100.0:
        p = 100.0
    return round(p, 1)


# ---------------------------------------------------------------------------
# Čitanje lokalnih tagova + filename fallback heuristika
# ---------------------------------------------------------------------------


def _parse_filename_fallback(path: Path) -> LocalTags:
    """Pokušava izvući osnovne tagove iz imena datoteke i foldera.

    Primjeri koje pokrivamo:
      - "01 - My Song.flac"                  -> track_no=1, title="My Song"
      - "Artist - Song.mp3"                  -> artist, title
      - "1999 - Artist - Song.flac"          -> year=1999, artist, title
      - "Artist - Album - Song.flac"         -> pokušaj artist + title, album iz foldera
    """
    stem = path.stem
    parent_album = path.parent.name
    artist: Optional[str] = None
    album: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    track_no: Optional[int] = None

    # Pattern 1: "NN - Title"
    m = re.match(r"^(\d{1,2})\s*-\s*(.+)$", stem)
    if m:
        try:
            track_no = int(m.group(1))
        except ValueError:
            track_no = None
        title = m.group(2).strip()

    # Pattern 2: "YYYY - Artist - Title"
    if not title:
        m2 = re.match(r"^(\d{4})\s*-\s*(.+?)\s*-\s*(.+)$", stem)
        if m2:
            try:
                year = int(m2.group(1))
            except ValueError:
                year = None
            artist = m2.group(2).strip()
            title = m2.group(3).strip()

    # Pattern 3: "Artist - Title"
    if not title or not artist:
        m3 = re.match(r"^(.+?)\s*-\s*(.+)$", stem)
        if m3:
            if not artist:
                artist = m3.group(1).strip()
            if not title:
                title = m3.group(2).strip()

    # Fallbackovi
    if not title:
        title = stem

    if not album and parent_album:
        album = parent_album

    return LocalTags(
        artist=artist,
        album=album,
        title=title,
        year=year,
        duration_sec=None,
        track_no=track_no,
    )


def read_local_tags(path: Path) -> LocalTags:
    """Čita osnovne tagove iz audio datoteke koristeći mutagen.

    Vraća minimalni set polja potrebnih za Spotify match.
    Ako tagovi ne postoje ili su vrlo oskudni, koristi se filename fallback.
    """
    audio = MutagenFile(path)
    if audio is None or getattr(audio, "tags", None) is None:
        logging.warning("Mutagen nije uspio pročitati tagove, koristim filename fallback: %s", path)
        return _parse_filename_fallback(path)

    tags = getattr(audio, "tags", None)

    def _get_first(tag_names: List[str]) -> Optional[str]:
        if not tags:
            return None
        for name in tag_names:
            if name in tags and tags[name]:
                v = tags[name]
                if isinstance(v, list):
                    return str(v[0])
                return str(v)
        return None

    artist = _get_first(["artist", "ARTIST", "TPE1"])
    album = _get_first(["album", "ALBUM", "TALB"])
    title = _get_first(["title", "TITLE", "TIT2"]) or path.stem
    year_str = _get_first(["date", "YEAR", "TDRC"])
    track_str = _get_first(["tracknumber", "TRCK"])

    year: Optional[int] = None
    if year_str:
        try:
            year = int(str(year_str)[:4])
        except ValueError:
            year = None

    track_no: Optional[int] = None
    if track_str:
        try:
            # formati: "3", "03", "3/10"
            track_no = int(str(track_str).split("/")[0])
        except ValueError:
            track_no = None

    duration_sec: Optional[float] = None
    info = getattr(audio, "info", None)
    if info is not None and hasattr(info, "length"):
        duration_sec = float(info.length)

    tags_obj = LocalTags(
        artist=artist,
        album=album,
        title=title,
        year=year,
        duration_sec=duration_sec,
        track_no=track_no,
    )

    # Ako nešto bitno nedostaje, pokušaj dopuniti iz filename-a
    fb = _parse_filename_fallback(path)

    if not tags_obj.artist and fb.artist:
        tags_obj.artist = fb.artist
    if not tags_obj.album and fb.album:
        tags_obj.album = fb.album
    if (not tags_obj.title or tags_obj.title == path.stem) and fb.title:
        tags_obj.title = fb.title
    if not tags_obj.year and fb.year:
        tags_obj.year = fb.year
    if not tags_obj.track_no and fb.track_no:
        tags_obj.track_no = fb.track_no

    logging.debug(
        "Lokalni tagovi za %s: artist=%r album=%r title=%r year=%r duration=%.2fs track_no=%r",
        path,
        tags_obj.artist,
        tags_obj.album,
        tags_obj.title,
        tags_obj.year,
        tags_obj.duration_sec or 0.0,
        tags_obj.track_no,
    )

    return tags_obj


# ---------------------------------------------------------------------------
# Spotify search & scoring (per track)
# ---------------------------------------------------------------------------


def search_best_match(sp: "spotipy.Spotify", tags: LocalTags) -> Optional[SpotifyTrackMeta]:
    """Pokušava pronaći najbolji Spotify track za zadane lokalne tagove."""
    if not tags.title:
        logging.error("Nema title taga, ne mogu raditi Spotify search.")
        return None

    query1_parts = []
    if tags.title:
        query1_parts.append(f'track:"{tags.title}"')
    if tags.artist:
        query1_parts.append(f'artist:"{tags.artist}"')
    query1 = " ".join(query1_parts) if query1_parts else tags.title

    logging.debug("Spotify search 1: %s", query1)
    result = sp.search(q=query1, type="track", limit=5)
    items = result.get("tracks", {}).get("items", [])

    if not items and tags.artist:
        # fallback: "artist title"
        query2 = f"{tags.artist} {tags.title}"
        logging.debug("Spotify search 2 (fallback): %s", query2)
        result = sp.search(q=query2, type="track", limit=5)
        items = result.get("tracks", {}).get("items", [])
        query1 = query2  # zapamti realno korišteni query

    if not items:
        logging.warning("Nema Spotify rezultata za: %s — %s", tags.artist, tags.title)
        return None

    norm_artist = _normalize(tags.artist or "")
    norm_title = _normalize(tags.title or "")

    best_item = None
    best_score = -1.0

    for item in items:
        stitle = item.get("name", "")
        sartists = [a.get("name", "") for a in item.get("artists", [])]
        album = item.get("album", {}) or {}
        release = album.get("release_date") or ""

        norm_stitle = _normalize(stitle)
        norm_sartists = [_normalize(a) for a in sartists]

        score = 0.0

        # Title match
        if norm_title and norm_title == norm_stitle:
            score += 3.0
        elif norm_title and (norm_title in norm_stitle or norm_stitle in norm_title):
            score += 2.0

        # Artist match
        if norm_artist and any(norm_artist == na for na in norm_sartists):
            score += 3.0
        elif norm_artist and any(norm_artist in na or na in norm_artist for na in norm_sartists):
            score += 2.0

        # Godina
        if tags.year and release:
            try:
                rel_year = int(release[:4])
                if rel_year == int(tags.year):
                    score += 1.0
                elif abs(rel_year - int(tags.year)) <= 1:
                    score += 0.5
            except ValueError:
                pass

        # Trajanje (gruba provjera, npr. tolerancija 3 sek)
        if tags.duration_sec and item.get("duration_ms"):
            try:
                diff = abs(tags.duration_sec - (item["duration_ms"] / 1000.0))
                if diff <= 1.5:
                    score += 1.0
                elif diff <= 3.0:
                    score += 0.5
            except Exception:
                pass

        logging.debug(
            "Candidate: %s — %s [%s] score=%.1f",
            ", ".join(sartists),
            stitle,
            release,
            score,
        )

        if score > best_score:
            best_score = score
            best_item = item

    if not best_item:
        logging.warning("Nije pronađen adekvatan kandidat za: %s — %s", tags.artist, tags.title)
        return None

    track_id = best_item["id"]
    track_url = best_item["external_urls"]["spotify"]
    album = best_item.get("album", {}) or {}
    album_id = album.get("id")
    album_url = album.get("external_urls", {}).get("spotify", "")
    album_name = album.get("name", "")
    release = album.get("release_date", "")

    isrc = None
    ext_ids = best_item.get("external_ids") or {}
    if "isrc" in ext_ids:
        isrc = ext_ids["isrc"]

    score_percent = _score_to_percent(best_score)

    meta = SpotifyTrackMeta(
        spotify_id=track_id,
        spotify_url=track_url,
        name=best_item.get("name", ""),
        artists=[a.get("name", "") for a in best_item.get("artists", [])],
        album_name=album_name,
        album_id=album_id or "",
        album_url=album_url,
        release_date=release,
        duration_ms=best_item.get("duration_ms", 0),
        disc_number=best_item.get("disc_number", 1),
        track_number=best_item.get("track_number", 0),
        explicit=best_item.get("explicit", False),
        popularity=best_item.get("popularity", 0),
        isrc=isrc,
        match_score_raw=round(best_score, 2),
        match_score_percent=score_percent,
        search_query=query1,
    )

    logging.info(
        "Match (%.1f%%): %s — %s  ->  %s — %s (%s)",
        score_percent,
        tags.artist,
        tags.title,
        ", ".join(meta.artists),
        meta.name,
        meta.release_date,
    )
    return meta


# ---------------------------------------------------------------------------
# JSON output helper
# ---------------------------------------------------------------------------


def build_spotify_json(
    audio_path: Path,
    tags: LocalTags,
    meta: Optional[SpotifyTrackMeta],
    unmatched_reason: Optional[str] = None,
    search_query: Optional[str] = None,
) -> Dict[str, Any]:
    """Gradi strukturu JSON-a koja će se zapisati u .stem.spotify.json."""
    audio_path = audio_path.resolve()
    stat = audio_path.stat()

    file_hash = compute_file_hash(audio_path)

    data: Dict[str, Any] = {
        "schema": {
            "type": "spotify_segment",
            "version": 1,
        },
        "file": {
            "path": str(audio_path),
            "stem": audio_path.stem,
            "size_bytes": stat.st_size,
            "mtime": int(stat.st_mtime),
            "hash_sha256": file_hash,
        },
        "local_tags": {
            "artist": tags.artist,
            "album": tags.album,
            "title": tags.title,
            "year": tags.year,
            "duration_sec": tags.duration_sec,
            "track_no": tags.track_no,
        },
    }

    if meta is not None:
        data["spotify"] = {
            "id": meta.spotify_id,
            "url": meta.spotify_url,
            "name": meta.name,
            "artists": meta.artists,
            "album": {
                "id": meta.album_id,
                "name": meta.album_name,
                "url": meta.album_url,
                "release_date": meta.release_date,
            },
            "duration_ms": meta.duration_ms,
            "disc_number": meta.disc_number,
            "track_number": meta.track_number,
            "explicit": meta.explicit,
            "popularity": meta.popularity,
            "isrc": meta.isrc,
        }
        data["match"] = {
            "status": "matched",
            "score_raw": meta.match_score_raw,
            "score_percent": meta.match_score_percent,
            "search_query": meta.search_query,
        }
    else:
        data["spotify"] = None
        data["match"] = {
            "status": "unmatched",
            "reason": unmatched_reason or "no_spotify_results_or_low_score",
            "search_query": search_query,
        }

    return data


def get_spotify_json_path(audio_path: Path) -> Path:
    """Vraća putanju do skrivenog .stem.spotify.json file-a uz audio."""
    audio_path = audio_path.resolve()
    stem = audio_path.stem
    json_name = f".{stem}.spotify.json"
    return audio_path.with_name(json_name)


# ---------------------------------------------------------------------------
# CLI komanda
# ---------------------------------------------------------------------------


def cmd_match(args: argparse.Namespace) -> None:
    audio_path = Path(args.path).expanduser()

    if not audio_path.exists():
        raise SystemExit(f"ERROR: audio datoteka ne postoji: {audio_path}")
    if not audio_path.is_file():
        raise SystemExit(f"ERROR: zadani --path nije file: {audio_path}")

    logging.info("Pokrećem match za: %s", audio_path)

    tags = read_local_tags(audio_path)
    if not tags.title:
        raise SystemExit("ERROR: nije moguće odrediti title za file (ni iz taga ni iz imena).")

    sp = build_spotify_client()
    meta = search_best_match(sp, tags)

    if meta is None:
        print("Nije pronađen adekvatan Spotify match.")
        if args.dry_run:
            logging.info("Dry-run uključen, NE zapisujem .spotify.json (unmatched).")
            return
        data = build_spotify_json(
            audio_path,
            tags,
            meta=None,
            unmatched_reason="no_spotify_results_or_low_score",
            search_query=None,
        )
        out_path = get_spotify_json_path(audio_path)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logging.info("Zapisao Spotify JSON (unmatched): %s", out_path)
        print(f"[OK] Zapisano unmatched u: {out_path}")
        return

    # CLI output (sažetak)
    print("=== MATCH RESULT ===")
    print(f"File        : {audio_path}")
    print(f"Title       : {tags.title}")
    print(f"Artist      : {tags.artist}")
    print(f"Album       : {tags.album}")
    print(f"Year        : {tags.year}")
    if tags.duration_sec:
        print(f"Duration    : {tags.duration_sec:.2f}s")
    else:
        print("Duration    : (unknown)")
    print("------------- Spotify -------------")
    print(f"Track name  : {meta.name}")
    print(f"Artists     : {', '.join(meta.artists)}")
    print(f"Album       : {meta.album_name} ({meta.release_date})")
    print(f"URL         : {meta.spotify_url}")
    print(f"Match score : {meta.match_score_percent:.1f}% (raw={meta.match_score_raw:.2f})")
    print(f"Query       : {meta.search_query}")

    if args.dry_run:
        logging.info("Dry-run uključen, NE zapisujem .spotify.json.")
        return

    data = build_spotify_json(audio_path, tags, meta)
    out_path = get_spotify_json_path(audio_path)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logging.info("Zapisao Spotify JSON: %s", out_path)
    print(f"\n[OK] Zapisano u: {out_path}")


# ---------------------------------------------------------------------------
# Argparse / main
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="modules.match",
        description=(
            "Per-track Spotify lookup modul. "
            "Čita tagove iz audio datoteke (--path), "
            "radi Spotify search i zapisuje skriveni .stem.spotify.json uz file."
        ),
    )
    p.add_argument(
        "--path",
        required=True,
        help="Puni path do audio datoteke za match.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Ne zapisuje JSON, samo ispisuje rezultat i log.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Detaljni log (DEBUG).",
    )
    p.set_defaults(func=cmd_match)
    return p


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    setup_logging(verbose=getattr(args, "verbose", False))
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
