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

## Installazione (sviluppo)

```bash
git clone https://github.com/strazzeracommerciale/karaokapp.git
cd karaoke_manager
pip install -r requirements.txt
python main.py
```

## Distribuzione su altro PC (Windows)

È possibile creare un **installer unico** che include l'app, Python, PyQt6, yt-dlp, ffmpeg e le librerie VLC — senza che l'utente finale installi nulla manualmente.

### Sul PC di build (una tantum)

Prerequisiti:

- Python 3.11+
- [VLC 64-bit](https://www.videolan.org/vlc/)
- ffmpeg nel PATH (`winget install Gyan.FFmpeg`)
- (consigliato) [Inno Setup 6](https://jrsoftware.org/isinfo.php) per generare un `.exe` di setup

```powershell
cd karaoke_manager
.\build\build_windows.ps1
```

Output:

| File/cartella | Descrizione |
|---------------|-------------|
| `dist\KaraokeManager\` | Versione portabile (copiabile su chiavetta) |
| `dist\KaraokeManager-Setup.exe` | Installer per l'utente finale (se Inno Setup è installato) |

### Sul PC di destinazione

1. Eseguire `KaraokeManager-Setup.exe` (oppure copiare la cartella `KaraokeManager`).
2. Avviare **KaraokeManager** dal menu Start o dal collegamento desktop.
3. Database, download e log restano in `data\`, `media\` e `logs\` accanto al programma.

Non serve Python, pip, VLC o ffmpeg separati: sono già inclusi nel pacchetto.

### Aggiornamenti online (portatile / installazione Windows)

Dall'**2.1** in poi, l'app installata con `KaraokeManager-Setup.exe`:

1. All'avvio controlla GitHub (al massimo ogni 24 h).
2. Se c'è una versione nuova, il pulsante diventa **Aggiorna a X.Y**.
3. **Un solo click** → download, chiusura app, installazione silenziosa (libreria e impostazioni restano).

**Prima installazione con aggiornamenti automatici:** se sul portatile hai ancora la 2.0, installa **una volta** `KaraokeManager-Setup.exe` della release **v2.1** (USB o download da GitHub). Da lì in poi basta il pulsante Aggiorna.

Pubblicare una release:

1. Allinea `APP_VERSION` in `config.py` e `build/installer.iss`.
2. Commit, push, tag `v2.1.0` (o `v2.1`), push del tag.
3. Il workflow `release-windows.yml` allega `KaraokeManager-Setup.exe` alla GitHub Release.

Per saltare la creazione dell'installer: `.\build\build_windows.ps1 -SkipInstaller`

Per VLC installato in percorso non standard: `.\build\build_windows.ps1 -VlcPath "D:\VLC"`

## macOS — in standby

La release macOS è **sospesa**. Su Mac compaiono troppi ostacoli (Gatekeeper, VLC Intel vs Apple Silicon, strumenti di sviluppo) rispetto al tempo disponibile.

**Piattaforma supportata per l'uso operativo: Windows** (`KaraokeManager-Setup.exe`).

Il codice resta cross-platform (`python main.py` in sviluppo su Mac resta possibile). Script e workflow GitHub per il `.dmg` restano nel repo ma la build **non parte più automaticamente**; si riprenderà solo se servirà davvero.

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
