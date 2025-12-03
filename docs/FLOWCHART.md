# FLOWCHART — Tok podataka u Z-Music Organizeru

Ovaj dokument opisuje cjelokupni tok podataka od lokalne audio datoteke
do popunjenog reda u bazi `tracks`.

---

## 1. Konceptualni dijagram toka

U pseudo-mermaid zapisu (npr. za GitHub markdown):

```mermaid
flowchart TD

    A[Početak] --> B[config.json učitan]
    B --> C{Postoji baza?}
    C -- Ne --> D[db_creator.py --create]
    C -- Da --> E[Provjera strukture baze]

    E --> F[Odabir root mape kolekcije]
    F --> G[Rekurzivno traženje audio datoteka]

    G --> H[Za svaku pjesmu: file_hash]
    H --> I[match.py - Spotify match]
    I -->|OK (score >= threshold)| J[meta_s JSON]
    I -->|Fail| L[match_errors.log]

    J --> K[analyze_track.py - audio analiza]
    K -->|OK| M[audio JSON]
    K -->|Fail| N[analysis_errors.log]

    M --> O[merge.py - spajanje JSONova]
    O -->|OK| P[final JSON]
    O -->|Fail| Q[merge_errors.log]

    P --> R[load.py - upis u bazu tracks]
    R -->|OK| S[tracks red popunjen]
    R -->|Fail| T[load_errors.log]

    S --> U{Ima još pjesama?}
    U -- Da --> G
    U -- Ne --> V[Kraj - baza popunjena]
```

---

## 2. Tekstualni opis korak-po-korak

1. **Inicijalizacija**
   - Učitava se `config.json`
   - Validiraju se putanje: baza, kolekcija, json folderi, log folderi
   - Ako baza ne postoji, kreira se (`db_creator.py --create`)

2. **Enumeracija kolekcije**
   - Skripta pronalazi sve podržane audio datoteke (npr. .mp3, .flac, .wav, .ogg)
   - Za svaku datoteku računa se `file_hash` i osnovni podaci (trajanje, samplerate itd.)

3. **Match korak (match.py)**
   - Na temelju tagova (artist, album, title) i trajanja radi se search na Spotifyu
   - Izračunava se `match_score` (0–1)
   - Ako je `match_score >= threshold`, sprema se `meta_s` JSON
   - Ako je `match_score < threshold`, zapisuje se u `match_errors.log` i prelazi na sljedeću pjesmu

4. **Analiza zvuka (analyze_track.py)**
   - Radi Essentia + Librosa + CLAP feature ekstrakciju
   - Rezultat se sprema kao `audio` JSON
   - U slučaju greške, upis u `analysis_errors.log`

5. **Merge (merge.py)**
   - Uzimaju se `meta_s` + `audio` JSON
   - Spajaju se u `final` JSON (jedinstveni pogled na pjesmu)
   - U slučaju nedostajućih JSON-ova ili grešaka, piše se u `merge_errors.log`

6. **Load u bazu (load.py)**
   - `final` JSON se mapira na polja tablice `tracks`
   - Ako `file_hash` već postoji:
     - radi se update postojećeg reda (npr. dodavanje analize ili Spotify podataka)
   - U slučaju greške, piše se u `load_errors.log`

7. **Ponovnost**
   - Koraci se ponavljaju za svaku pjesmu u kolekciji
   - Skripta je idempotentna: ponovno pokretanje ne duplicira zapise, nego nadograđuje

---

## 3. Seed pipeline (visoka razina)

Seed pipeline ima dva dijela:

### `seed_generate.py`

- Čita postojeće podatke iz `tracks` tablice i/ili user input
- Preko Spotify recommendations endpointa generira listu novih Spotify ID-eva
- Sprema ih u queue datoteku (npr. `queue/seed_queue.json`)

### `seed_process.py`

Za svaki entry u queue-u:

1. Skida audio datoteku vanjskim alatom (npr. downloader koji koristi Spotify ili YT kao izvor)
2. Radi isti pipeline kao za lokalnu pjesmu:
   - match (po potrebi)
   - analiza
   - merge
   - load
3. Briše ili označava entry kao obrađen

Ovaj tok osigurava da i pjesme koje nemamo lokalno u kolekciji mogu biti u bazi s punim setom featurea.

---

Ovaj flowchart i tekst služe kao glavni referentni dokument za razumijevanje kako podaci teku kroz cijeli sustav.
