# Z-Music Organizer

Z-Music Organizer je modularni sustav za organizaciju i analizu velike lokalne glazbene kolekcije
(10k–100k pjesama) uz integraciju sa Spotify API-jem.

Ovaj repozitorij sadrži:

- **specifikaciju sustava** (TODO_v2.md)
- **početni kostur projekta** (prazne mape i `modules/` direktorij)
- **README / ROADMAP / FLOWCHART / Spotify API plan**
- Jedinstven tok: *lokalna kolekcija → Spotify match → audio analiza → merge → baza*

> Napomena: ovo je skeleton projekta, bez implementacijskog koda. Služi kao početna točka
> za razvoj i verzioniranje.

---

## 1. Glavna ideja

Cilj sustava je:

- Popisati i analizirati **svaku lokalnu audio datoteku** u kolekciji
- Povezati je s odgovarajućom pjesmom na **Spotifyu** (ako postoji)
- Spremiti **sve metapodatke** i **audio featurese** u jednu centralnu bazu (SQLite `tracks` tablica)
- Omogućiti pametno preporučivanje novih pjesama (seed + recommendations)
- Biti **otporan na prekide**, siguran od korupcije i jednostavan za ponovno pokretanje

---

## 2. Moduli sustava (visoka razina)

1. **Database modul**
   - skripta za kreiranje, brisanje i info o bazi (`db_creator.py`)
   - jedna tablica: `tracks` (lokalna, Spotify, analiza)

2. **Config modul**
   - radi s konfiguracijskom datotekom (`config.json`)
   - centralno mjesto za sve putanje i globalne opcije

3. **Spotify OAuth modul**
   - generira i osvježava Spotify token (`spotify_oauth.py`)
   - sprema token i informacije u `oauth.json`

4. **Match modul**
   - pronalazi najbliži Spotify zapis lokalnoj pjesmi (`match.py`)
   - računa `match_score` i stvara `meta_s` JSON

5. **Analysis modul**
   - radi audio analizu (`analyze_track.py`)
   - generira `audio` JSON (Essentia, Librosa, CLAP, FAZA 2 featurei)

6. **Merge modul**
   - spaja `meta_s` + `audio` u `final` JSON (`merge.py`)

7. **Load modul**
   - učitava `final` JSON u bazu (`load.py`)

8. **Import modul**
   - master skripta za punjenje baze iz lokalne kolekcije (`import_music.py`)

9. **Seed modul**
   - **seed_generate.py** → generira queue preporučenih pjesama sa Spotifya
   - **seed_process.py** → obrađuje queue, skida, analizira i upisuje u bazu

Detaljna specifikacija polja, tokova i pravila nalazi se u `TODO_v2.md`.

---

## 3. Struktura direktorija

Kostur projekta izgleda ovako:

```text
project_root/
├── README.md
├── TODO_v2.md
├── ROADMAP.md
├── database/
│   └── (tracks.db će biti ovdje)
├── logs/
│   └── (log datoteke po modulima)
├── json/
│   ├── meta_s/
│   ├── audio/
│   └── final/
├── queue/
│   └── (datoteke s queue-om, npr. seed_queue.json)
├── modules/
│   ├── db_creator.py        (za kreiranje/brisanje/info baze)
│   ├── config.py            (rad s config.json)
│   ├── spotify_oauth.py     (OAuth login / refresh)
│   ├── match.py             (Spotify match za 1 pjesmu)
│   ├── analyze_track.py     (audio analiza 1 pjesme)
│   ├── merge.py             (merge meta_s + audio → final)
│   ├── load.py              (upis final JSON-a u bazu)
│   ├── import_music.py      (batch punjenje kolekcije)
│   ├── seed_generate.py     (generiranje anbefaljenih ID-eva)
│   └── seed_process.py      (obrada queue-a)
└── docs/
    ├── FLOWCHART.md
    └── SPOTIFY_API_PLAN.md
```

Ove `.py` datoteke u skeletonu u početku neće imati implementaciju, već služe kao ulazne točke.

---

## 4. Ključni koncepti

- **Jedna tablica `tracks`** – nema fragmentacije podataka po više tablica
- **Jedan `file_hash`** – stabilan identitet pjesme
- **Tri JSON sloja** za svaku pjesmu:
  - `meta_s` (Spotify meta)
  - `audio` (analitički featurei)
  - `final` (merge svega, jedini izvor istine za Load)
- **Idempotentni import** – ponovno pokretanje ne duplira zapise, nego nadograđuje

Za dubinske detalje vidi `TODO_v2.md`.

---

## 5. ROADMAP i verzioniranje

Pogledaj `ROADMAP.md` za plan verzija (v1.x, v2.x…).  
Analiza ima svoju verziju: `analysis_version`, definiranu u configu.

---

## 6. Flowchart i API plan

- `docs/FLOWCHART.md` – opis cjelokupnog toka podataka (tekst + pseudo-flowchart)
- `docs/SPOTIFY_API_PLAN.md` – opis Spotify endpointa, rate-limit strategije i cache politike

---

## 7. Kako započeti (konceptualno)

1. Napraviti `config.json` pomoću `config.py`
2. Kreirati bazu (`db_creator.py --create`)
3. Napraviti inicijalni Spotify OAuth (`spotify_oauth.py`)
4. Implementirati i testirati:
   - `match.py` za jednu testnu pjesmu
   - `analyze_track.py` za istu pjesmu
   - `merge.py` + `load.py`
5. Tek nakon toga proširiti na cijelu kolekciju kroz `import_music.py`.

Ovaj repozitorij je točka polaska za taj razvojni proces.
