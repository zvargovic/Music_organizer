
#!/usr/bin/env python3
"""
load.py — FULL FLATTEN verzija

Cilj: uzeti final JSON (.final.json) i upisati ŠTO VIŠE POLJA u tablicu tracks.
Ne ograničavamo se na 4 polja, već popunjavamo sve stupce koji postoje u bazi
i za koje znamo ili možemo pogoditi iz strukture final JSON-a.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config import get_main_db_path


# ---------------------------------------------------------------------
# DB path helper
# ---------------------------------------------------------------------

def get_db_path(custom: Optional[str]) -> Path:
    if custom:
        p = Path(custom).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return get_main_db_path()


# ---------------------------------------------------------------------
# Pronalaženje final JSON-a
# ---------------------------------------------------------------------

def _guess_final_json_path(base_path: Path) -> Path:
    p = base_path

    # ako je direktno JSON → koristi taj
    if p.suffix.lower() == ".json":
        return p

    candidates = [
        # stari .stem.final.json patterni
        p.parent / f"{p.name}.stem.final.json",
        p.with_suffix(".stem.final.json"),
        # novi skriveni .XXX.final.json
        p.parent / f".{p.stem}.final.json",
        p.parent / f".{p.name}.final.json",
    ]

    for c in candidates:
        if c.is_file():
            return c

    raise SystemExit(
        f"[ERROR] Ne mogu pronaći FINAL JSON za: {p}\n"
        f"Pokušani kandidati:\n" + "".join(f"  - {c}\n" for c in candidates)
    )


def _load_final_json(final_path: Path) -> Dict[str, Any]:
    try:
        with final_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise SystemExit(f"[ERROR] Neispravan JSON u {final_path}: {e}") from e


# ---------------------------------------------------------------------
# Shema baze
# ---------------------------------------------------------------------

def _get_tracks_columns(conn: sqlite3.Connection):
    cur = conn.execute("PRAGMA table_info(tracks)")
    cols = [r[1] for r in cur.fetchall()]
    if not cols:
        raise SystemExit("[ERROR] Tablica 'tracks' ne postoji u bazi.")
    # preferiraj file_hash > file_path > id za upsert
    key_col = None
    for k in ("file_hash", "file_path", "id"):
        if k in cols:
            key_col = k
            break
    return cols, key_col


# ---------------------------------------------------------------------
# Infer hash i path iz final JSON-a
# ---------------------------------------------------------------------

def _infer_file_hash(obj: Dict[str, Any]) -> Optional[str]:
    # 1) direktno na rootu
    for k in ("file_hash", "hash_sha256", "hash"):
        v = obj.get(k)
        if isinstance(v, str) and v:
            return v

    # 2) file.hash_sha256
    file_info = obj.get("file")
    if isinstance(file_info, dict):
        for k in ("hash_sha256", "file_hash", "hash"):
            v = file_info.get(k)
            if isinstance(v, str) and v:
                return v

    return None


def _infer_file_path(obj: Dict[str, Any], cli_path: Path) -> Optional[str]:
    # ako CLI nije JSON → to je audio path
    if cli_path.suffix.lower() != ".json":
        return str(cli_path.resolve())

    # inače probaj iz file.path
    file_info = obj.get("file")
    if isinstance(file_info, dict):
        v = file_info.get("path")
        if isinstance(v, str) and v:
            return v

    return None


# ---------------------------------------------------------------------
# Flat map JSON -> stupci tracks
# ---------------------------------------------------------------------

def _build_record(
    obj: Dict[str, Any],
    cols,
    cli_path: Path,
    final_json_path: Path,
) -> Tuple[Dict[str, Any], str, Any]:
    colset = set(cols)
    row: Dict[str, Any] = {}

    # razbij JSON na sekcije
    file_info   = obj.get("file")        or {}
    tags_local  = obj.get("local_tags")  or {}
    spotify     = obj.get("spotify")     or {}
    match_info  = obj.get("match")       or {}
    features    = obj.get("features")    or {}
    genre_info  = obj.get("genre")       or {}
    mood_info   = obj.get("mood")        or {}
    instr_info  = obj.get("instruments") or {}

    # --- file_hash / file_path ---
    file_hash = _infer_file_hash(obj)
    file_path = _infer_file_path(obj, cli_path)

    if "file_hash" in colset:
        if not file_hash:
            raise SystemExit("[ERROR] final JSON nema hash_sha256/file_hash koji mogu koristiti za file_hash.")
        row["file_hash"] = file_hash

    if "file_path" in colset:
        if not file_path:
            raise SystemExit("[ERROR] ne mogu odrediti file_path ni iz CLI puta ni iz JSON-a.")
        row["file_path"] = file_path

    # --- identitet filea ---
    if "file_size" in colset:
        row["file_size"] = file_info.get("size_bytes")
    if "mtime" in colset:
        row["mtime"] = file_info.get("mtime")

    # --- osnovni tagovi ---
    if "title" in colset:
        row["title"] = tags_local.get("title") or spotify.get("name")
    if "artist" in colset:
        artist = tags_local.get("artist")
        if not artist and isinstance(spotify.get("artists"), list) and spotify["artists"]:
            artist = spotify["artists"][0]
        row["artist"] = artist
    if "album" in colset:
        album = tags_local.get("album")
        if not album and isinstance(spotify.get("album"), dict):
            album = spotify["album"].get("name")
        row["album"] = album
    if "album_artist" in colset:
        # ako nemamo posebnog album_artist, koristi artist
        row["album_artist"] = tags_local.get("album_artist") or row.get("artist")
    if "track_number" in colset:
        row["track_number"] = tags_local.get("track_no") or spotify.get("track_number")
    if "disc_number" in colset:
        row["disc_number"] = spotify.get("disc_number")
    if "year" in colset:
        year = tags_local.get("year")
        if not year and isinstance(spotify.get("album"), dict):
            rd = spotify["album"].get("release_date")
            if isinstance(rd, str) and len(rd) >= 4 and rd[:4].isdigit():
                year = int(rd[:4])
        row["year"] = year
    if "duration_sec" in colset:
        dur = tags_local.get("duration_sec")
        if dur is None:
            dur = features.get("duration")
        if dur is None and spotify.get("duration_ms"):
            dur = spotify["duration_ms"] / 1000.0
        row["duration_sec"] = dur
    if "genre" in colset:
        g = tags_local.get("genre")
        if not g and isinstance(genre_info, dict):
            g = genre_info.get("primary")
        row["genre"] = g

    # --- Spotify meta ---
    if "spotify_id" in colset:
        row["spotify_id"] = spotify.get("id")
    if "spotify_url" in colset:
        row["spotify_url"] = spotify.get("url")
    if "spotify_preview_url" in colset:
        row["spotify_preview_url"] = spotify.get("preview_url")
    if "spotify_popularity" in colset:
        row["spotify_popularity"] = spotify.get("popularity")
    if "spotify_isrc" in colset:
        row["spotify_isrc"] = spotify.get("isrc")
    if "spotify_album_id" in colset and isinstance(spotify.get("album"), dict):
        row["spotify_album_id"] = spotify["album"].get("id")
    if "spotify_artist_ids" in colset:
        # nemamo ID-jeve, samo imena → ostavi None ili koristi comma-separated liste imena
        arts = spotify.get("artists")
        if isinstance(arts, list):
            row["spotify_artist_ids"] = ",".join(arts)
    if "spotify_match_score" in colset:
        # koristi percent ili raw ako postoji
        score = match_info.get("score_percent")
        if score is None:
            score = match_info.get("score_raw")
        row["spotify_match_score"] = score

    # --- Sažetak audio analize / features ---
    # direct mapping ako postoje istoimeni stupci
    for k, v in features.items():
        if k in colset and k not in row:
            row[k] = v

    # posebni aliasi: tempo -> bpm, key -> key, energy -> energy, itd.
    if "bpm" in colset and "bpm" not in row:
        row["bpm"] = features.get("tempo")
    if "key" in colset and "key" not in row:
        row["key"] = features.get("key")
    if "loudness_db" in colset and "loudness_db" not in row:
        row["loudness_db"] = features.get("loudness_db")
    if "danceability" in colset and "danceability" not in row:
        row["danceability"] = features.get("danceability")
    if "energy" in colset and "energy" not in row:
        row["energy"] = features.get("energy")
    if "valence" in colset and "valence" not in row:
        row["valence"] = features.get("valence")
    if "acousticness" in colset and "acousticness" not in row:
        row["acousticness"] = features.get("acousticness")
    if "instrumentalness" in colset and "instrumentalness" not in row:
        row["instrumentalness"] = features.get("instrumentalness")
    if "tempo_confidence" in colset and "tempo_confidence" not in row:
        row["tempo_confidence"] = features.get("tempo_confidence")

    # --- mood / instruments ako imamo posebne stupce ---
    if isinstance(mood_info, dict):
        if "mood_valence" in colset:
            row["mood_valence"] = mood_info.get("valence")
        if "mood_arousal" in colset:
            row["mood_arousal"] = mood_info.get("arousal")
        if "mood_label" in colset:
            row["mood_label"] = mood_info.get("label")
    if isinstance(instr_info, dict):
        if "lead_instrument" in colset:
            row["lead_instrument"] = instr_info.get("lead")
        if "bass_type" in colset:
            row["bass_type"] = instr_info.get("bass")
        if "drums_pattern" in colset:
            row["drums_pattern"] = instr_info.get("drums")

    # --- putevi do JSON datoteka ---
    if "final_path" in colset:
        row["final_path"] = str(final_json_path.resolve())

    # pokušaj pogoditi audio/meta_s putanje prema imenu final JSON-a
    stem_final = final_json_path.name.replace(".final.json", "")
    parent = final_json_path.parent
    guess_audio = parent / f"{stem_final}.analysis.json"
    guess_meta = parent / f"{stem_final}.spotify.json"
    if "audio_path" in colset and guess_audio.exists():
        row["audio_path"] = str(guess_audio)
    if "meta_s_path" in colset and guess_meta.exists():
        row["meta_s_path"] = str(guess_meta)

    # --- verzije / flagovi ---
    if "analysis_version" in colset and "analysis_version" not in row:
        row["analysis_version"] = 1
    if "spotify_meta_version" in colset and "spotify_meta_version" not in row:
        row["spotify_meta_version"] = 1
    if "is_missing" in colset and "is_missing" not in row:
        row["is_missing"] = 0
    if "is_duplicate" in colset and "is_duplicate" not in row:
        row["is_duplicate"] = 0

    # odredi ključ za upsert
    if "file_hash" in colset and file_hash:
        key_col = "file_hash"
        key_val = file_hash
    elif "file_path" in colset and file_path:
        key_col = "file_path"
        key_val = file_path
    else:
        raise SystemExit("[ERROR] ne mogu odrediti ključ za upsert (ni file_hash ni file_path nisu dostupni).")

    return row, key_col, key_val


# ---------------------------------------------------------------------
# UPSERT
# ---------------------------------------------------------------------

def _upsert_track(
    conn: sqlite3.Connection,
    data: Dict[str, Any],
    key: str,
    val: Any,
    dry: bool,
) -> str:
    cur = conn.execute(f"SELECT id FROM tracks WHERE {key} = ?", (val,))
    row = cur.fetchone()
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")

    d = dict(data)

    if row is None:
        d.setdefault("added_at", now)
        d["updated_at"] = now
        cols = list(d.keys())
        vals = [d[c] for c in cols]
        if not dry:
            conn.execute(
                f"INSERT INTO tracks ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                vals,
            )
        return "dry-run insert" if dry else "inserted"
    else:
        d["updated_at"] = now
        d.pop("added_at", None)
        d.pop(key, None)
        if d and not dry:
            cols = list(d.keys())
            vals = [d[c] for c in cols] + [val]
            conn.execute(
                f"UPDATE tracks SET {', '.join(f'{c}=?' for c in cols)} WHERE {key}=?",
                vals,
            )
        return "dry-run update" if dry else "updated"


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        prog="load.py",
        description="Upis final JSON-a (.final.json) u tablicu tracks (flatten na sve dostupne stupce).",
    )
    ap.add_argument("--path", required=True, help="Audio datoteka ili final JSON")
    ap.add_argument("--db", help="Custom path do SQLite baze (opcionalno)")
    ap.add_argument("--dry-run", action="store_true", help="Ne zapisuj u bazu, samo simuliraj.")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    cli_path = Path(args.path).expanduser().resolve()
    final_json_path = _guess_final_json_path(cli_path)

    if args.verbose:
        print(f"[INFO] Final JSON: {final_json_path}")

    obj = _load_final_json(final_json_path)
    db_path = get_db_path(args.db)

    if not db_path.is_file():
        raise SystemExit(
            f"[ERROR] Baza ne postoji: {db_path}\n"
            f"        Kreiraj je prvo pomoću: python -m modules.db_creator create"
        )

    conn = sqlite3.connect(db_path)
    try:
        cols, _key_col = _get_tracks_columns(conn)
        record, key, val = _build_record(obj, cols, cli_path, final_json_path)

        if args.verbose:
            print(f"[INFO] Upsert ključ: {key}={val}")
            print(f"[INFO] Polja za upis ({len(record)}):")
            for k in sorted(record.keys()):
                print(f"  - {k}")

        status = _upsert_track(conn, record, key, val, args.dry_run)

        if not args.dry_run:
            conn.commit()

        print(f"[OK] {status} ({key}={val})")

        # statistika uvijek
        cur = conn.execute("SELECT COUNT(*) FROM tracks")
        (count,) = cur.fetchone()
        print(f"[STATS] Ukupno redova u tablici tracks: {count}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
