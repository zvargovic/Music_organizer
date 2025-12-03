# SPOTIFY API PLAN — Z-Music Organizer

Ovaj dokument definira kako Z-Music Organizer koristi Spotify Web API,
koje endpointove, kako se nosi s rate-limitima i kako se ponaša u slučaju
grešaka ili nedostupnosti servisa.

---

## 1. Ciljevi integracije sa Spotifyjem

1. **Pronalaženje točnog Spotify zapisa** za lokalnu audio datoteku.
2. **Dohvat metapodataka** (album, artisti, trajanje, popularnost, žanrovi…).
3. **Dohvat preporuka** (recommendations) za seed pipeline.
4. (Opcionalno kasnije) **Sinkronizacija praćenih artista** i novih izdanja.

Svi pozivi idu preko `spotify_oauth.py` modula koji osigurava valjan token.

---

## 2. Glavni endpointi

### 2.1 Search endpoint

Za `match.py`:

- Endpoint: `/v1/search`
- Metoda: `GET`
- Parametri (query):
  - `q`: kombinacija artist + track + album (prema dostupnim tagovima)
  - `type=track`
  - `limit` (npr. 5–10)
- Primarna svrha: lista kandidata za izračun `match_score`.

`match_score` uzima u obzir:
- naziv pjesme
- izvođača
- album
- trajanje (sekunde)
- godinu izdanja (ako je dostupna)

### 2.2 Track details endpoint

Za `match.py` (nakon izbora pobjedničkog kandidata) i/ili naknadni sync:

- Endpoint: `/v1/tracks/{id}`
- Metoda: `GET`
- Podaci koji se koriste:
  - `name`
  - `duration_ms`
  - `popularity`
  - `album` (id, name, release_date)
  - `artists` (lista id + name)
  - pripadajući external URLs

Ovi podaci idu u `meta_s` JSON i završavaju u `tracks` tablici pod Spotify grupom polja.

### 2.3 Recommendations endpoint

Za `seed_generate.py`:

- Endpoint: `/v1/recommendations`
- Metoda: `GET`
- Parametri:
  - `seed_tracks` / `seed_artists` / `seed_genres`
  - limit (npr. 20–50)
  - dodatni parametri (npr. target_danceability, target_energy…) – opcionalno

Rezultat:
- lista novih trackova (id, name, artists, album, itd.)
- ti ID-evi se spremaju u queue datoteku za `seed_process.py`.

### 2.4 (Opcionalno kasnije) Followed artists / New releases

Za naprednije seed funkcije može se koristiti:

- `/v1/me/following?type=artist`
- `/v1/artists/{id}/albums`
- `/v1/browse/new-releases`

Ovo nije nužno za inicijalnu verziju, ali je planirano u kasnijim fazama.

---

## 3. Rate-limit strategija

Spotify Web API ima rate-limit (HTTP 429).  
Točan limit ovisi o aplikaciji i prometu, ali osnovna pravila su:

1. **Poštujemo `Retry-After` header**:
   - Ako dobijemo 429, čitamo `Retry-After` (u sekundama)
   - Pauziramo pozive prema Spotifyju barem toliko sekundi
   - Nakon toga nastavljamo

2. **Batch obrada s pauzama**:
   - `match.py` i `import_music.py`:
     - nakon X uspješnih poziva (npr. 50–100), radi se kratka pauza (npr. 1–2 sekunde)
   - `seed_generate.py`:
     - koristi manji broj poziva, fokus na kvalitetu, ne na kvantitetu

3. **Backoff strategija**:
   - kod ponavljanih 429 odgovora koristi se exponential backoff (npr. 5s, 10s, 20s…)
   - broj retryja je ograničen (npr. max 5 pokušaja po operaciji)

4. **Logiranje rate-limit događaja**:
   - svaki 429 zapisuje se u poseban log (npr. `logs/spotify_rate_limit.log`)
   - log sadrži:
     - vrijeme
     - tip operacije (match/search/recommendations)
     - `Retry-After` vrijednost

---

## 4. Error handling i fallback

Tipične situacije i ponašanje:

1. **HTTP 401 (Unauthorized / token expired)**  
   - `spotify_oauth.py` osvježava token (refresh_token flow)
   - ponavlja se originalni upit
   - ako ni tada ne uspije → log + odustajanje od tog upita

2. **HTTP 404 (Not found)**  
   - npr. track je uklonjen sa Spotifyja
   - zapisuje se u log (npr. `match_errors.log` ili `seed_errors.log`)
   - prelazi se na sljedeću pjesmu

3. **Timeout / mrežni problemi**  
   - ponavlja se upit s backoffom (npr. do 3 puta)
   - ako i dalje ne uspije → log + skip

4. **Neispravni podaci (npr. release_date u čudnom formatu)**  
   - parsiranje mora biti robustno
   - u slučaju greške zapisuje se sirova vrijednost u `analysis_notes` ili poseban field
   - pipeline se ne ruši

---

## 5. Cache politika (opcionalno ali preporučeno)

Da bi se smanjio broj upita prema Spotifyju, preporučuje se uvesti jednostavan cache sloj:

- Key: kombinacija (artist, track, album, trajanje)
- Value: najbolji pronađeni Spotify track ID + osnovni meta podaci

Cache implementacija (konceptualno):

- jednostavna SQLite tablica ili JSON datoteka u `json/cache` direktoriju
- prije svakog novog searcha provjeriti cache
- ako postoji zapis s dovoljno visokim scoreom, preskočiti API search

Prednosti:
- manje poziva prema Spotifyju
- brži match pipeline za velike kolekcije
- otpornost ako Spotify privremeno padne (podaci su već lokalno keširani)

---

## 6. Sigurnosni aspekti

- OAuth podaci (`client_id`, `client_secret`, `refresh_token`) ne smiju se logirati
- `oauth.json` se čuva u konfiguriranoj lokaciji i po potrebi se može dodati u `.gitignore`
- Logovi ne smiju sadržavati osjetljive identifikatore korisnika (user IDs, e-mail itd.)

---

## 7. Sažetak

Ovaj plan osigurava da:

- Sve integracije sa Spotifyjem imaju jasnu svrhu i ograničen scope
- Rate-limiti se poštuju i ne dolazi do blokiranja
- Svi problemi se logiraju, ali ne ruše pipeline
- Sustav je spreman za skaliranje na desetke tisuća pjesama bez kršenja Spotify politikâ.

Ovaj dokument treba koristiti kao referentnu točku tijekom implementacije svih modula koji komuniciraju sa Spotifyjem.
