# ROADMAP v2 — Z-Music Organizer

Ovaj dokument je *jedini* koji se koristi za označavanje napretka (DONE).

Sve stavke su podijeljene po verzijama i modulima.

---

# ✅ v1.0.0 — Osnovni Pipeline (MVP)

## 1. Baza i konfiguracija
- [ ] db_creator.py — kreiranje / brisanje / info baze
- [ ] config.py — kreiranje i validacija config.json

## 2. Spotify autentikacija
- [ ] spotify_oauth.py — login, refresh, info

## 3. Match modul
- [ ] match.py — pronalaženje Spotify ID-a + meta_s JSON

## 4. Analiza audio datoteka
- [ ] analyze_track.py — Essentia + Librosa + CLAP + FAZA2 featurei

## 5. Merge modul
- [ ] merge.py — spajanje meta_s + audio → final JSON

## 6. Load modul
- [ ] load.py — upis final JSON-a u bazu

## 7. Import music pipeline
- [ ] import_music.py — puni bazu iz lokalne kolekcije, idempotentno

---

# 🚀 v1.1.0 — Hardening i stabilnost
- [ ] JSON log format (standardiziran)
- [ ] Retry mehanizam kroz sve module
- [ ] Error kategorije (match / analysis / merge / load)

---

# 🔍 v1.2.0 — Seed pipeline (generiranje + procesiranje)

## 1. Generiranje queue-a
- [ ] seed_generate.py — Spotify recommendations → queue JSON

## 2. Procesiranje queue-a
- [ ] seed_process.py — skidanje → match → analiza → merge → load

---

# 🎵 v1.3.0 — Napredna analiza (FAZA 2)
- [ ] beat_density
- [ ] rhythm_complexity
- [ ] chord_complexity
- [ ] instrument detection improvements
- [ ] genre/mood refinements

---

# 🖥 v2.0.0 — User-facing sloj
- [ ] REST API server (lokalni)
- [ ] Web UI za pretraživanje baze
- [ ] Playlist builder

---

# 📘 PROGRESS LOG

## 2025-??-??  
(ovdje se upisuju datumi i što je označeno kao DONE)
