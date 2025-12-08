# ROADMAP v2 — Z-Music Organizer
Ovaj dokument je *jedini* koji se koristi za označavanje napretka (DONE).  
Sve stavke su podijeljene po verzijama i modulima.

# ✅ v1.0.0 — Osnovni Pipeline (MVP)

## 1. Baza i konfiguracija
- [x] db_creator.py — kreiranje / info / drop / clear (03.12.2025 — DONE)
- [x] config.py — centralne putanje za bazu i projekt (03.12.2025 — DONE)

## 2. Spotify autentikacija
- [x] spotify_oauth.py — interaktivni wizard + login + token info (03.12.2025 — DONE)

## 3. Match modul
- [x] match.py — per-track Spotify lookup (`--path`) + skriveni `.stem.spotify.json` + `hash_sha256` identitet (04.12.2025 — DONE)

## 4. Analiza audio datoteka
- [x] audio_analyze.py — CLAP + Librosa analiza (global + segment embedding), jazz-focused žanrovi/mood/instrumenti, `.analysis.json`, `--info` tablica, per-track sažetak (04.12.2025 — DONE)
- [x] AUDIO_ANALYSIS_MODULE.md — dokumentacija audio analize i JSON strukture (04.12.2025 — DONE)

## 5. Merge modul
- [x] merge.py — per-track spajanje skrivenog `.spotify.json` + vidljivog `.analysis.json` → skriveni `.final.json` (04.12.2025 — DONE)

## 6. Load modul
- [x] load.py — per-track upis `.final.json` u bazu (`tracks` tablica), automatski mapping hash/path + flatten na sve dostupne stupce (05.12.2025 — DONE)

# 7. Import music pipeline — IMPLEMENTIRANO
STATUS: DONE

## 7.1. Cilj
Automatski prolaz kroz cijelu lokalnu kolekciju.  
Per-track pipeline:
MATCH → AUDIO ANALYZE → MERGE → LOAD
Pipeline mora biti idempotentan, automatiziran, rate-limit safe i stabilan.

## 7.2. Idempotentnost
MATCH:
- samo ako ne postoji `.stem.spotify.json` ili `--force-match`

AUDIO:
- samo ako ne postoji `.stem.audio.json` ili `--force-audio`

MERGE:
- ako `.final.json` ne postoji ili je stariji od ulaza ili `--force-merge`

LOAD:
- uvijek kada `.final.json` postoji (INSERT OR REPLACE)

## 7.3. Spotify Rate Limit Zaštita
- minimalni razmak: 1–5 s
- 429 → sleep(60), nakon 5x prekini
- svaki track ionako traje ≥ 5 s → prirodni throttle

## 7.4. Struktura import_music.py
ARGPARSE:
--base-path  
--dry-run  
--max-tracks  
--force-match --force-audio --force-merge  
--skip-match --skip-audio --skip-merge --skip-load  
--info  

HELPER FUNKCIJE:
is_audio_file(path)  
derive_stem(path)  
newer_than(a,b)  
Stats klasa  
log(...)  

HOOKOVI NA CORE MODULE:
modules.match.match_track(path)  
modules.audio_analyze.analyze_track(path)  
modules.merge.merge_track(stem_base)  
modules.load.load_track(final_json_path)  

## 7.5. Glavna petlja
1. Rekurzivni scan `--base-path`
2. Filtriranje audio ekstenzija
3. Sortiranje
4. process_track(audio_path)
5. Summary:

[STATS]
Total tracks:  
Matched:  
Analyzed:  
Merged:  
Loaded:  
Failed:  
Spotify calls:  

## 7.6. Očekivani rezultat
- Import brz, efikasan i deterministički
- Re-run radi samo na promjenama
- Spotify API nikad nije flooded
- Baza reflektira `.final.json`


# 8. Downloader modul — IMPLEMENTIRANO
# 9. Download queue modul — IMPLEMENTIRANO
STATUS: DONE

- [x] download_queue.py — high-level queue wrapper nad download.py; čita batch JSON-ove iz `get_downloader_batch_dir()` i za svaki poziva `modules.download batch` s `--base-path` i `--dry-run` podrškom (07.12.2025 — DONE)

STATUS: DONE

- [x] download.py — FAZA 1: CLI skeleton (track/album/artist/batch/info), bez realnog downloada
- [x] download.py — FAZA 2: batch + provjera postojećih fajlova (AUDIO_EXTS) + dry-run
- [x] download.py — FAZA 2b: integracija sa spotdl (realni download u TMP_DIR, before/after diff, premještanje u Artist/Year/Album/Artist - Title.ext)
    - batch: puni pipeline za 1+ trackova
    - track: minimalni wrapper (dummy meta, ali koristi isti download engine)
    - album/artist: za sada kostur (SIM output, bez pravog Spotify API)
  (06.12.2025 — DONE)

# 🚀 v1.1.0 — Hardening i stabilnost
- [ ] JSON log format
- [ ] Retry mehanizam
- [ ] Error kategorije po fazama

# 🔍 v1.2.0 — Seed pipeline
- [ ] seed_generate.py — recommendations → queue JSON
- [ ] seed_process.py — skidanje → match → analiza → merge → load

# 🎵 v1.3.0 — Napredna analiza (FAZA 2)
- [ ] beat_density
- [ ] rhythm_complexity
- [ ] chord_complexity
- [ ] instrument detection improvements
- [ ] genre/mood refinements


# 🧠 10. Brain Feeder — v1.4.0

## 10.0. Preduvjeti
- [ ] Dodati stupce u bazu:
  - `has_audio INTEGER NOT NULL DEFAULT 1`
  - `want_file INTEGER NOT NULL DEFAULT 1`
- [ ] Migracija postojeće baze (`ALTER TABLE ... DEFAULT 1`)
- [ ] load.py:
  - nakon INSERT/UPDATE dodati:
    `UPDATE tracks SET has_audio = 1 WHERE sha = ?`
- [ ] want_file NE dira load.py (odluka brain feedera ili default baze)

## 10.1. Brain Feeder Core (zasebna app/proces)
- [ ] Napraviti `brain_feeder.py` (zasebni entry-point)
- [ ] CLI:
  - `--once`
  - `--loop`
  - `--dry-run`
  - `--info`
- [ ] DB helper konekcija (WAL + timeout + kratke transakcije)
- [ ] Retry na `database is locked`

## 10.2. V1 Logika — upravljanje postojećim trackovima
- [ ] `brain_feeder_rules.json` (favorite_artists, baseline pravila)
- [ ] engine:
  - učitaj pravila
  - pronađi pogođene trackove
  - izračunaj deltu
  - UPDATE `want_file`
- [ ] Dry-run: ispis promjena
- [ ] Real mode: upis u DB

## 10.3. Downloader integracija
- [ ] Missing audio → koristiti:
  `WHERE has_audio = 0 AND want_file = 1`
- [ ] Statistika:
  - total_missing
  - wanted_missing
- [ ] (opcija) source filter za `bf_source`

## 10.4. V2 — novi zapisi iz Spotify feedera
- [ ] Dodati `bf_source` u tracks (local/follow/recommendation/manual)
- [ ] Brain feeder stvara stub zapise:
  - spotify_id
  - artist, album, title, godina
  - `has_audio = 0`
  - `want_file` prema pravilima
  - `bf_source = 'followed_artist'`
- [ ] Downloader automatski vidi stubove i ubacuje ih u batch

## 10.5. V3 — napredni scoring
- [ ] mood/genre/instrument scoring → `want_file` odluke
- [ ] `bf_score` (0–100)
- [ ] automatski threshold
- [ ] generiranje reporta (`.md` / `.txt`)


# 🖥 v2.0.0 — User-facing sloj
- [ ] REST API
- [ ] Web UI
- [ ] Playlist builder

# 📘 PROGRESS LOG
## 2025-12-06
- Downloader modul (download.py FAZA 2b: spotdl integracija + TMP diff + premještanje u finalni folder) — DONE
- download.py — batch CLI progress bar (plava trakica, current/total) — DONE

## 2025-12-03
- DB Creator, config, OAuth — DONE  

## 2025-12-04
- Match, AudioAnalyze, Merge — DONE  

## 2025-12-05
- Load — DONE  
- Dodan Import Pipeline u roadmap  
- Import završen  

## 2025-12-07
- download_queue.py — DONE  
- Dodane kolone `has_audio` i `want_file` u plan  
- Brain Feeder — dodan kompletan modul u roadmap  