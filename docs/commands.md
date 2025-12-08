# Z-Music Organizer — Komande

## 1. Općenite Git komande

### Inicijalizacija repozitorija (ako nije već kloniran)
```bash
git clone https://github.com/zvargovic/Music_organizer.git .
```

### Provjera statusa
```bash
git status
```

### Dodavanje svih izmjena
```bash
git add .
```

### Commit izmjena
```bash
git commit -m "Opis promjene"
```

### Slanje na GitHub (push)
```bash
git push
```

### Povlačenje novih promjena (pull)
```bash
git pull
```

---

## 2. Komande za module

### 🔹 **db_creator.py**

#### Kreiraj bazu (ako već postoji → error)
```bash
python -m modules.db_creator create
```

#### Kreiraj bazu i prepiši postojeću
```bash
python -m modules.db_creator create --force
```

#### Ispiši info o bazi
```bash
python -m modules.db_creator info
```

#### Obriši datoteku baze (traži potvrdu)
```bash
python -m modules.db_creator drop
```

#### Obriši datoteku baze bez pitanja
```bash
python -m modules.db_creator drop --yes
```

#### Očisti tablicu tracks, ali ostavi strukturu baze (traži potvrdu)
```bash
python -m modules.db_creator clear
```

#### Isto, ali bez pitanja
```bash
python -m modules.db_creator clear --yes
```

---

### 🔹 **spotify_oauth.py**

#### Prvi setup + login (interaktivni wizard)
```bash
python -m modules.spotify_oauth
```
- prvi put: traži **Client ID**, **Client Secret** i **Redirect URI**
- automatski otvara browser za Spotify login / authorize
- sprema credove u `.hidden/spotify_credentials.json`
- sprema OAuth token + refresh_token u `.hidden/spotify_oauth_token.json`

- svaki sljedeći put:
  - koristi postojeći token
  - po potrebi ga automatski osvježi (refresh)
  - provjeri `current_user` i ispiše osnovne informacije

#### Pregled tokena (lokacija, sadržaj, expiry)
```bash
python -m modules.spotify_oauth info
```
- ispisuje putanje do cred/token fajlova
- ispisuje raw `token_info` kao JSON
- prikazuje `expires_at` u human-readable formatu (npr. `za 59m`)
- provjerava `current_user()` i ispisuje stanje korisnika

---

### 🔹 **match.py**

Per-track Spotify lookup na temelju lokalnog fajla (tagovi + trajanje) i zapis skrivenog `.spotify.json` uz audio.

#### Match jedne pjesme
```bash
python -m modules.match --path "/put/do/Artist/Album/01 - Track.flac"
```

#### Match s detaljnijim ispisom
```bash
python -m modules.match --path "/put/do/Artist/Album/01 - Track.flac" --verbose
```

---

### 🔹 **audio_analyze.py**

Analiza audio datoteke (CLAP + Librosa, jazz-focused features) i zapis vidljivog `.analysis.json` uz audio.

#### Analiza jedne pjesme
```bash
python -m modules.audio_analyze --path "/put/do/Artist/Album/01 - Track.flac"
```

#### Info mod (sažetak + tablica bez ponovnog računanja)
```bash
python -m modules.audio_analyze --path "/put/do/Artist/Album/01 - Track.flac" --info
```

---

### 🔹 **merge.py**

Spajanje `.spotify.json` + `.analysis.json` u skriveni `.final.json` (zajednički `hash_sha256` identitet).

#### Merge jedne pjesme
```bash
python -m modules.merge --path "/put/do/Artist/Album/01 - Track.flac"
```

#### Merge s detaljnijim ispisom
```bash
python -m modules.merge --path "/put/do/Artist/Album/01 - Track.flac" --verbose
```

---

### 🔹 **load.py**

Učitavanje finalnog JSON-a (`.final.json`) u tablicu `tracks`. Automatski nalazi `.final.json` na temelju audio fajla,
mapira `hash_sha256` → `file_hash`, određuje `file_path`, te puni sve dostupne stupce (file/meta/spotify/features/...).

#### Dry-run (bez upisa, samo simulacija + pregled polja)
```bash
python -m modules.load --path "/put/do/Artist/Album/01 - Track.flac" --dry-run --verbose
```

#### Stvarni upis u bazu
```bash
python -m modules.load --path "/put/do/Artist/Album/01 - Track.flac" --verbose
```

#### Upis u custom bazu (ako ne koristiš default iz config.py)
```bash
python -m modules.load --path "/put/do/Artist/Album/01 - Track.flac" --db "/put/do/neke_drugacije_baze.db"
```

---

### 🔹 **import_music.py**

High-level import pipeline: prolaz kroz lokalnu kolekciju i za svaku pjesmu pokreće
`match → analyze → merge → load`, uz idempotentnost i kontrolirani Spotify rate.

#### Import cijele kolekcije (koristi root iz config.py, npr. `MUSIC_BASE_DIR`)
```bash
python import_music.py
```

#### Import od specificiranog foldera (npr. jedan artist / jedan album)
```bash
python import_music.py --base-path "/Volumes/HDD2/Music/351 Lake Shore Drive/2011/Provencale"
```

#### Limitiraj broj pjesama (npr. za testiranje)
```bash
python import_music.py --base-path "/Volumes/HDD2/Music" --max-tracks 100
```

#### Info mod — sažetak nakon importa (stats + JSON sažetak)
```bash
python import_music.py --base-path "/Volumes/HDD2/Music/351 Lake Shore Drive/2011/Provencale" --max-tracks 3 --info
```

- `--base-path`  → odakle pipeline kreće (root kolekcije ili pod-folder)
- `--max-tracks` → stani nakon N pjesama (korisno za probe)
- `--info`       → dodatno ispiše JSON sa statistikama (matched / analyzed / merged / loaded / failed / spotify_calls / elapsed_sec)

---

## Ovdje će se dodavati komande za sve buduće module:
- scanner.py
- analyze_track.py
- spotify_oauth.py (proširenja)
- itd.

Svaki modul će imati svoju podsekciju kao db_creator.py gore.
---

### 🔹 **download.py**

Downloader modul za skidanje audio datoteka preko **spotdl** alata.
Radi u više modova (track / album / artist / batch), ali je trenutno
u potpunosti implementiran i testiran za **batch** i **track**.

#### Info o downloader konfiguraciji
```bash
python -m modules.download info
```
- ispisuje `BATCH_DIR`, `TMP_DIR`, `LOG_DIR`
- pokaže vrijednost `ZMUSIC_MUSIC_ROOT` ako je postavljen

#### Batch download (test na praznom folderu, dry-run)
```bash
python -m modules.download batch \
  --json data/download_batches/test_batch.json \
  --base-path /Volumes/HDD2/Music_TEST_EMPTY \
  --dry-run \
  --info
```
- čita listu trackova iz `test_batch.json`
- provjerava postoji li već audio fajl na odredištu
- u **dry-run** modu ne zove spotdl, samo javlja što bi se radilo

#### Batch download (realni download)
```bash
python -m modules.download batch \
  --json data/download_batches/test_batch.json \
  --base-path /Volumes/HDD2/Music_TEST_EMPTY \
  --info
```
- koristi **before/after diff** u `TMP_DIR` da pronađe koji je audio fajl novi
- novi fajl automatski premješta u strukturu:
  `Artist/Year/Album/Artist - Title.ext` ispod `--base-path`

#### Track download (single ID ili URL, dummy meta)
```bash
# preko ID-a
python -m modules.download track \
  --id 1zWU8xqh32lGNz2lVElNL1 \
  --base-path /Volumes/HDD2/Music_TEST_EMPTY \
  --info

# preko URL-a
python -m modules.download track \
  --url https://open.spotify.com/track/1zWU8xqh32lGNz2lVElNL1 \
  --base-path /Volumes/HDD2/Music_TEST_EMPTY \
  --info
```
- za sada koristi `Unknown Artist/Unknown Album/Unknown Track` kao meta,
  ali koristi isti download engine kao batch

> Napomena: `--dry-run` se može dodati na bilo koju komandu da samo simulira bez downloada.

---

### 🔹 **download_queue.py**

High-level *queue* modul iznad postojećeg `download.py`. Ne skida ništa sam,
nego za svaki batch JSON poziva:

```bash
python -m modules.download batch --json <file> --base-path <root> [--dry-run] --info
```

JSON-ovi se očekuju u direktoriju koji vraća `get_downloader_batch_dir()`.

#### Queue: odradi SVE pending batch JSON-ove

```bash
python -m modules.download_queue queue \\
  --path /Volumes/HDD2/Music \\
  --dry-run
```

- traži sve `*.json` u batch direktoriju koji **nemaju** sufiks `.json.done`
- za svaki JSON poziva `modules.download batch` s `--base-path` i `--dry-run`
- u **dry-run** modu ne skida ništa, samo se simulira poziv downloadera
- bez `--dry-run`:
  - svi batch-evi s `exit=0` se rename-aju u `*.json.done`
  - batch-evi s greškom ostaju u folderu za kasnije ponovno pokretanje

Primjer realnog queue run-a:

```bash
python -m modules.download_queue queue \\
  --path /Volumes/HDD2/Music
```

#### Batch: odradi JEDAN batch JSON preko download.py

```bash
python -m modules.download_queue batch \\
  --json data/download_batches/artist_album_20251207_174322.json \\
  --path /Volumes/HDD2/Music \\
  --dry-run
```

- korisno za debug pojedinog batch fajla
- bez `--dry-run` radi stvarni download
