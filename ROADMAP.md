# ROADMAP — Z-Music Organizer

Ovaj dokument opisuje plan verzioniranja i razvojne faze sustava.

---

## Verzije

### v1.0.0 — Osnovni pipeline (MVP)

Cilj: dobiti **stabilan, deterministički i robustan** pipeline za punjenje baze iz lokalne kolekcije.

Uključuje:

- Jedna tablica `tracks` u SQLite bazi
- `config.json` i `config.py`
- `db_creator.py` (create / delete / clear / info)
- `spotify_oauth.py` s ručnim loginom i automatskim refreshom
- `match.py` koji:
  - pronalazi najbolji Spotify zapis za lokalnu pjesmu
  - generira `meta_s` JSON
- `analyze_track.py` koji:
  - radi Essentia + Librosa + CLAP analizu
  - generira `audio` JSON
- `merge.py` (spaja `meta_s` + `audio` → `final` JSON)
- `load.py` (učitava `final` JSON u `tracks` tablicu)
- `import_music.py` (batch obrada cijele kolekcije)
- osnovni logovi po modulima
- definirani `file_hash` algoritam
- `analysis_version` u configu

Kriterij završetka:
- 1000+ pjesama uspješno procesirano bez rušenja sustava
- ponovno pokretanje ne duplira zapise
- logovi jasno pokazuju sve neuspjele upite / analize

---

### v1.1.0 — Hardening i ergonomija

- Dodatni sanity checkovi prije upisa u bazu
- Bolji error log format (npr. JSON log entries)
- Statistički izvještaji (broj uspješnih/neuspješnih pjesama)
- Opcija ograničavanja broja istodobnih obrada (npr. u import_music)
- Poboljšane poruke za korisnika na CLI-ju

---

### v1.2.0 — Seed pipeline (Spotify recommendations)

- `seed_generate.py`:
  - generira queue Spotify ID-eva na temelju:
    - postojećih pjesama u bazi
    - praćenih artista
    - žanrova / raspoloženja
- `seed_process.py`:
  - prolazi queue
  - skida audio (npr. koristeći vanjski downloader alat)
  - pokreće match/analizu/merge/load na temelju queue-a
- Safe handling:
  - robustan format queue datoteke
  - detektiranje duplikata u queue-u

---

### v1.3.0 — Napredne analize (FAZA 2 proširenje)

- dodatni featurei (beat_density, chord_complexity, rhythm_complexity, itd.)
- preciznija klasifikacija žanra / raspoloženja / instrumenata
- evaluacija kvalitete featurea i korekcija heuristika

`analysis_version` se podiže (npr. s `v1.0.0` na `v1.1.0`), a stari zapisi ostaju kompatibilni.

---

### v2.0.0 — User-facing sloj (GUI / API)

- REST API ili lokalni HTTP servis za upite prema bazi
- jednostavno web sučelje za filtriranje i preslušavanje
- generiranje custom playlisti na temelju featurea

Ovo je odvojena faza i ne utječe na jezgru pipelinea osim što čita istu bazu.

---

## Policy verzioniranja

- **Major verzija (X.0.0)** — velike promjene u arhitekturi ili shemi baze
- **Minor verzija (1.X.0)** — nova funkcionalnost koja je backward kompatibilna
- **Patch verzija (1.0.X)** — bugfixi, optimizacije, bez promjene formata podataka

`analysis_version` se versionira **neovisno** (npr. `analysis_v1.0.0`).

---

## Preporučeni redoslijed rada

1. Implementirati sve za v1.0.0
2. Testirati na malom uzorku (100–200 pjesama)
3. Tek onda pustiti veliku kolekciju (10k+)
4. Nakon stabilnosti MVP-a, krenuti na seed pipeline (v1.2.0)
