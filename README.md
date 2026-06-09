# KaraokeManager

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.7-green)
![VLC](https://img.shields.io/badge/VLC-64--bit-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

Applicazione desktop professionale per la gestione di serate karaoke e DJ.
Unifica ricerca, download, riproduzione e playlist in un'unica interfaccia,
con supporto dual monitor e consolle DJ dedicata.

## Funzionalità principali

- Ricerca unificata locale + YouTube
- Download automatico in background
- Dual monitor (schermo esterno HDMI)
- Consolle DJ separata
- Playlist karaoke e DJ
- Sottofondo automatico durante le pause

## Requisiti

- Python 3.11+
- VLC 64-bit installato e nel PATH di sistema
- ffmpeg (richiesto da yt-dlp per la conversione audio/video)

## Installazione

```bash
git clone https://github.com/strazzeracommerciale/karaokapp.git
pip install -r requirements.txt
python main.py
```

## Struttura del progetto

Architettura a 4 layer:

| Layer | Cartella | Responsabilità |
|-------|----------|----------------|
| **UI** | `ui/` | Widget PyQt6, finestre, segnali utente |
| **Service** | `services/` | Logica applicativa, orchestrazione, stato |
| **Engine** | `engines/` | VLC, yt-dlp, ricerca fuzzy, display |
| **Data** | `db/` | Schema SQLite, migrazioni, persistenza |

Documentazione dettagliata: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Licenza

Distribuito sotto licenza MIT. Vedi [LICENSE](LICENSE).
