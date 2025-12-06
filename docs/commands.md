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


## Ovdje će se dodavati komande za sve buduće module:
- scanner.py
- match.py
- analyze_track.py
- merge.py
- load.py
- import_music.py
- spotify_oauth.py (proširenja)
- itd.

Svaki modul će imati svoju podsekciju kao db_creator.py gore.
