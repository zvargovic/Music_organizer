# Audio analiza modul (jazz verzija, utišani logovi + sažetak)

Ovaj modul implementira kompletan audio analizator za Z-Music Organizer, s fokusom na jazz i jazz-bliske žanrove.

Dodatno u ovoj verziji:
- utišani su laion_clap / Transformers warningi (Roberta, trening, progress barovi)
- utišan je ispis "Loaded ..." iz CLAP modela (redirect stdout/stderr tijekom `load_ckpt()`)
- nakon svake analize ispisuje se sažetak:
  - vrijeme obrade
  - putanja JSON-a
  - trajanje, tempo, key, energy, beat_density
  - žanr + alt žanr + confidence
  - mood tag + valence/arousal
  - lead instrument, bass tip, drums pattern

Ostalo kao prije:

- Faza 1: CLAP embedding (global + segmentirani)
- Faza 2: Librosa feature-i
- Faza 3: Zero-shot jazz žanrovi, mood, instrumenti

## CLI (podsjetnik)

```bash
python -m modules.audio_analyze --path "/music/Artist/Album/track.flac"
python -m modules.audio_analyze --folder "/music/Artist"
python -m modules.audio_analyze --folder "/music/Artist" --info
```
