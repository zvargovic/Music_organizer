# FLOWCHART — Tok podataka u Z-Music Organizeru

Ovaj dokument opisuje cjelokupni tok podataka od lokalne audio datoteke
do popunjenog reda u bazi `tracks`, prema novoj **per-track** logici:

> 1 pjesma → match → analyse → merge → load → sljedeća pjesma

Svaki bitan segment (skripta) radi nad **jednom** audio datotekom, uz argument `--path`,
a glavni pipeline `import_music.py` orkestrira prolaz kroz cijelu kolekciju.

JSON datoteke za pojedinu pjesmu su skrivene (Unix hidden) i nalaze se **uz audio datoteku**:

- audio: `/Music/Artist/Album/01 - Track.flac`  (primjer)
- Spotify meta: `/Music/Artist/Album/.01 - Track.spotify.json`
- audio analiza: `/Music/Artist/Album/01 - Track.flac.analysis.json`
- finalni JSON: `/Music/Artist/Album/.01 - Track.final.json`

Napomena: svi segment JSON-ovi (.spotify.json, .audio.json, .final.json) sadrže `hash_sha256` kao glavni identitet audio datoteke kroz cijeli pipeline.

---

## 1. Konceptualni dijagram toka (per-track pipeline)

U pseudo-mermaid zapisu (npr. za GitHub markdown):

```mermaid
flowchart TD

    A[Početak] --> B[config.py učitan / validirane putanje]
    B --> C{Postoji baza?}
    C -- Ne --> D[db_creator.py --create<br/>kreiranje tablice tracks]
    C -- Da --> E[Provjera strukture baze]
    D --> E
    E --> F[import_music.py start]

    F --> G[Nađi sljedeću audio datoteku u kolekciji]
    G --> H{Postoji još neobrađenih datoteka?}
    H -- Ne --> Z[Kraj - baza popunjena / nema više posla]
    H -- Da --> I[match.py --path<br/>Spotify lookup → .spotify.json]

    I -->|Fail| I1[logs/match/*.log<br/>skip na sljedeću datoteku]
    I --> J[audio_analyze.py --path<br/>audio analiza → .analysis.json]

    J -->|Fail| J1[logs/analyse/*.log<br/>skip na sljedeću datoteku]
    J --> K[merge.py --path<br/>spajanje → .final.json]

    K -->|Fail| K1[logs/merge/*.log<br/>skip na sljedeću datoteku]
    K --> L[load.py --path<br/>upis u DB (tablica tracks)]

    L -->|Fail| L1[logs/load/*.log<br/>skip na sljedeću datoteku]
    L --> G
```

Objašnjenja:

- `stem` = ime audio datoteke bez ekstenzije (npr. `01 - Track`)
- JSON datoteke su skrivene (`.` na početku imena) kako ne bi smetale u folderu albuma
- svaki modul (`match.py`, `audio_analyze.py`, `merge.py`, `load.py`) radi SAMO nad jednom pjesmom i podržava argument `--path`.

---

## 2. Tekstualni opis korak-po-korak (per-track)

### 2.1. Inicijalizacija

1. Učitava se konfiguracija iz `config.py` (putanje baze, kolekcije, json/log foldera, itd.).
2. Ako baza ne postoji, pokreće se `db_creator.py --create` i kreira se tablica `tracks`.
3. Provjerava se struktura baze (postojanje tablice, osnovna shema).

### 2.2. Import loop (`import_music.py`)

1. `import_music.py` pronalazi **sljedeću** neobrađenu audio datoteku u kolekciji.
   - detekcija “obrađeno/neobrađeno” može biti na temelju:  
     - postojanja `.final.json`, ili  
     - statusnog polja u bazi (`tracks`), ili  
     - kombinacije oba pristupa (detalj implementacije je u samom modulu).
2. Ako nema više datoteka → pipeline završava.
3. Ako postoji datoteka, njezin puni path prosljeđuje se u sljedeće segmente kao `--path`.

### 2.3. Match korak (`match.py --path /.../Track.flac`)

- Na temelju tagova (artist, album, title, year, trajanje) radi se pretraga na Spotifyu.
- Izračunava se `match_score` (npr. 0–100%) koji govori koliko je rezultat siguran.
- Uspješan rezultat se sprema u **skriveni** JSON:
  - `.spotify.json` uz audio datoteku.
- U slučaju greške ili preniskog match score-a:
  - bilježi se zapis u `logs/match/` (npr. `match_errors.log`),
  - trenutna datoteka se preskače i import loop ide na sljedeću.

### 2.4. Analiza zvuka (`audio_analyze.py --path /.../Track.flac`)

- Radi Essentia + Librosa + CLAP (i FAZA2 feature-e kad budu implementirani).
- Rezultat se sprema kao skriveni JSON:
  - `.analysis.json` uz audio datoteku.
- U slučaju greške:
  - zapis u `logs/analyse/`,
  - trenutna datoteka se preskače.

### 2.5. Merge (`merge.py --path /.../Track.flac`)

- Čita `.spotify.json` + `.analysis.json` uz audio datoteku.
- Spaja ih u jedan **final** JSON:
  - `.final.json` uz audio datoteku.
- Rješava eventualne konflikte i osigurava konzistentnu shemu.
- U slučaju da nedostaje jedan od input JSON-ova ili se detektira greška:
  - zapis u `logs/merge/`,
  - trenutna datoteka se preskače.

### 2.6. Load u bazu (`load.py --path /.../Track.flac`)

- Čita `.final.json` za zadani `--path`.
- Mapira polja iz final JSON-a u kolone tablice `tracks`.
- Ako za `file_hash` (ili drugi identifikator) zapis već postoji:
  - radi se **update** (npr. dodavanje analize ili Spotify podataka).
- U slučaju greške:
  - zapis u `logs/load/`,
  - trenutna datoteka se preskače.

### 2.7. Idempotentnost

- Ponovno pokretanje `import_music.py` ne smije duplicirati zapise u bazi.
- Ako `.final.json` već postoji i zapis u `tracks` je potpun, modul može:
  - detektirati da je pjesma već obrađena,
  - preskočiti je,
  - ili eventualno ponuditi “rebuild” flag (npr. `--force-rebuild` na pipelineu).

---

## 3. Seed pipeline (visoka razina)

Seed pipeline i dalje ima dva dijela, ali sada **koristi isti per-track pipeline** kao i lokalna kolekcija.

### 3.1. `seed_generate.py`

- Čita postojeće podatke iz tablice `tracks` i/ili user input.
- Preko Spotify recommendations endpointa generira listu novih Spotify ID-eva.
- Rezultat sprema u queue datoteku (npr. `queue/seed_queue.json`).

### 3.2. `seed_process.py`

Za svaki entry u queue-u:

1. Skida audio datoteku vanjskim alatom (npr. downloader koji koristi Spotify ili YT kao izvor).
2. Poziva **isti per-track pipeline** kao i za lokalnu pjesmu, samo što izvor nije lokalna kolekcija nego queue:
   - `match.py` (po potrebi, ako već nemamo sve meta podatke).
   - `audio_analyze.py`.
   - `merge.py`.
   - `load.py`.
3. Briše ili označava entry u queue-u kao obrađen.

Time je osigurano da i pjesme koje nisu dio originalne lokalne kolekcije mogu proći kroz cijeli pipeline i završiti u bazi s punim setom featurea.

---

Ovaj flowchart i tekst služe kao glavni referentni dokument za razumijevanje kako podaci teku kroz cijeli sustav
u **novoj, segment-based per-track arhitekturi**.
