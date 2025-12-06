# TODO_v2 — Z-Music Organizer (segment-based pipeline)

Ovaj dokument opisuje konkretne zadatke za implementaciju **per-track** pipelinea.
Status *završenosti* (DONE) i dalje se službeno označava samo u `ROADMAP_v2.md`.
Ovdje su zadaci i pod-moduli koje treba implementirati / doraditi.

---

## A. JSON i path konvencije

- [ ] Implementirati per-track JSON imena i lokacije (skriveni uz audio):
  - `.stem.spotify.json`
  - `.stem.audio.json`
  - `.stem.final.json`
- [ ] Dodati helper funkcije (npr. `utils/paths.py`) za računanje:
  - audio `stem` iz `--path`
  - putanje do odgovarajućih JSON datoteka
- [ ] Dogovoriti i dokumentirati minimalnu shemu za:
  - `spotify` JSON (Spotify segment)
  - `audio` JSON (analiza zvuka)
  - `final` JSON (merge rezultat)

---

## B. Match modul — `modules/match.py`

Cilj: pronaći Spotify ID + meta podatke za **jednu** pjesmu (preko `--path`) i zapisati ih u `.stem.spotify.json`.

Zadaci:
- [ ] CLI sučelje:
  - podržati `python -m modules.match --path "/full/path/to/Track.flac"`
  - opcionalno `--dry-run` (ne piše JSON, samo ispisuje rezultat)
  - opcionalno `--verbose` (detaljan log i scoring)
- [ ] Integracija s `spotify_oauth.py`:
  - koristiti postojeće credentiale i token cache iz `.hidden/`
- [ ] Logika matchanja:
  - [ ] čitanje osnovnih tagova (artist, album, title, year, duration)
  - [ ] Spotify search s heuristikom za najbolji rezultat
  - [ ] izračun `match_score` (%)
  - [ ] jasni CLI output (prikaz postotka i izabranog tracka)
- [ ] Output:
  - [ ] zapis u `.stem.spotify.json` (skriveni file uz audio)
  - [ ] logovi u `logs/match/` (uključujući failove i preniski score)

---

## C. Analiza audio datoteka — `modules/analyse_track.py`

Cilj: iz jedne audio datoteke (preko `--path`) izračunati feature-e i zapisati ih u `.stem.audio.json`.

Zadaci:
- [ ] CLI sučelje:
  - `python -m modules.analyse_track --path "/full/path/to/Track.flac"`
  - opcionalno `--dry-run`, `--verbose`
- [ ] Audio loading + normalizacija (sample rate, mono/stereo, sl.)
- [ ] Feature set FAZA 1 (osnovni):
  - [ ] trajanje, RMS/energy, tempo, loudness
  - [ ] osnovni spectral feature-i (centroid, rolloff, flatness)
  - [ ] CLAP embedding (global)
- [ ] Kasnije proširenje FAZA 2 (napredni feature-i — vidi ROADMAP):
  - beat_density, rhythm_complexity, chord_complexity, itd.
- [ ] Output:
  - [ ] zapis u `.stem.audio.json`
  - [ ] logovi u `logs/analyse/`

---

## D. Merge modul — `modules/merge.py`

Cilj: za zadani `--path` pročitati `.stem.spotify.json` + `.stem.audio.json` i spojiti ih u `.stem.final.json`.

Zadaci:
- [ ] CLI sučelje:
  - `python -m modules.merge --path "/full/path/to/Track.flac"`
- [ ] Validacija:
  - [ ] provjera da oba input JSON-a postoje
  - [ ] provjera osnovnih polja (npr. isti file_hash / path)
- [ ] Spajanje:
  - [ ] definirati konačnu shemu `final` JSON-a (npr. `{"file": {...}, "spotify": {...}, "audio": {...}}`)
  - [ ] briga o kompatibilnosti s tablicom `tracks`
- [ ] Error handling:
  - [ ] logiranje problema u `logs/merge/`
  - [ ] jasne poruke kad neki od inputa nedostaje

---

## E. Load modul — `modules/load.py`

Cilj: pročitati `.stem.final.json` za `--path` i upisati / ažurirati jedan red u tablici `tracks`.

Zadaci:
- [ ] CLI sučelje:
  - `python -m modules.load --path "/full/path/to/Track.flac"`
- [ ] Veza s bazom (`database/tracks.db`):
  - [ ] helper u `config.py` za DB path
  - [ ] funkcije za `INSERT` / `UPDATE`
- [ ] Logika upisa:
  - [ ] jedinstveni ključ (npr. `file_hash` ili canonical path)
  - [ ] ako zapis ne postoji → `INSERT`
  - [ ] ako zapis postoji → `UPDATE` (nadogradnja podataka)
- [ ] Error handling:
  - [ ] logovi u `logs/load/`

---

## F. Import music pipeline — `import_music.py`

Cilj: proći kroz cijelu lokalnu kolekciju **jednim prolazom**, i za svaku datoteku pokrenuti per-track pipeline:

> match → analyse → merge → load

Zadaci:
- [ ] CLI sučelje:
  - `python import_music.py` (puni prolaz)
  - opcionalno `--root PATH` (override root kolekcije)
  - opcionalno `--force` (ignorira postojeće `.final.json` i rebuild-a)
- [ ] Enumeracija kolekcije:
  - [ ] rekurzivno traženje podržanih audio ekstenzija
  - [ ] integracija s `config.py` za root path
- [ ] Logika statusa (obrađeno / neobrađeno):
  - [ ] prepoznavanje da `.stem.final.json` već postoji
  - [ ] eventualna provjera da je zapis u bazi kompletan
- [ ] Orkestracija:
  - [ ] za svaku datoteku pozvati interni API modula:
    - `match` segment (umjesto uvijek CLI poziva)
    - `analyse` segment
    - `merge` segment
    - `load` segment
  - [ ] za greške koristiti standardizirane logove, ali nastaviti s idućom pjesmom
- [ ] Idempotentnost:
  - [ ] višestruko pokretanje pipelinea ne smije stvarati duplikate u DB-u
  - [ ] `--force` flag za ručni rebuild pojedinih dijelova (npr. ponovna analiza)

---

## G. Logovi i error handling

Zadaci:
- [ ] Dogovoriti standardni format poruka u logovima (prefiksi `[INFO]`, `[WARN]`, `[ERROR]`)
- [ ] Uspostaviti strukturu foldera:
  - `logs/match/`
  - `logs/analyse/`
  - `logs/merge/`
  - `logs/load/`
- [ ] Po mogućnosti uvesti JSON log format (vezano uz ROADMAP v1.1.0)

---

## H. Testiranje i dev quality-of-life

Zadaci:
- [ ] Za svaki modul osigurati barem minimalni skup “smoke test” komandi (npr. u `docs/commands.md`):
  - `match.py --path SOMEFILE`
  - `analyse_track.py --path SOMEFILE`
  - `merge.py --path SOMEFILE`
  - `load.py --path SOMEFILE`
- [ ] Dodati primjere outputa u dokumentaciju (kratki isječci CLI outputa)
- [ ] Osigurati da se svi moduli mogu koristiti i **samostalno** (ručno) i kao dio `import_music.py` pipelinea.
