# Build macOS — KaraokeManager

> **Stato: IN STANDBY** — distribuzione `.dmg` sospesa. Usare Windows per l'installazione operativa.

Guida tecnica conservata per un eventuale ripresa futura.

La build è gestita da **GitHub Actions** (workflow `.github/workflows/build-macos.yml`):

- Trigger: push su `main`, tag `v*`, oppure manuale (**Actions → Build macOS → Run workflow**)
- Due job paralleli: **arm64** (M1/M2/M3) e **x86_64** (Intel)
- Artifact scaricabili per 90 giorni

Non serve Python/VLC/ffmpeg sul Mac locale. Vedi [`INSTALL_MACOS.md`](INSTALL_MACOS.md) per installare l’app.

## Build locale (opzionale)

| Aspetto | Decisione | Motivo |
|---------|-----------|--------|
| Formato | `.dmg` drag-and-drop | Semplice per uso interno, niente firma richiesta |
| Dati utente | `~/Library/Application Support/KaraokeManager/` | Il bundle in `/Applications` non è scrivibile; è lo standard macOS |
| Binari app | Accanto all'eseguibile nel `.app` (`vlc/`, `bin/ffmpeg`) | Read-only, come su Windows |
| Architettura | `universal2` di default | Un solo `.dmg` per Mac Intel e Apple Silicon |

## Prerequisiti (Mac di build)

1. **macOS Ventura 13+**
2. **Python 3.11 o 3.12** — per `universal2` installare il installer **universal2** da [python.org](https://www.python.org/downloads/macos/) (non solo arm64 da Homebrew)
3. **VLC** — [videolan.org](https://www.videolan.org/vlc/) → `/Applications/VLC.app`
4. **ffmpeg** — `brew install ffmpeg`
5. **Xcode Command Line Tools** — `xcode-select --install`

## Build

```bash
cd karaoke_manager
chmod +x build/build_macos.sh
./build/build_macos.sh              # universal2 (consigliato)
./build/build_macos.sh arm64        # solo Apple Silicon
./build/build_macos.sh x86_64       # solo Intel
SKIP_DMG=1 ./build/build_macos.sh   # solo .app, senza .dmg
```

Output:

- `dist/KaraokeManager.app`
- `dist/KaraokeManager-1.0.2-macOS-universal2.dmg`

## Installazione (utente finale)

1. Aprire il `.dmg`
2. Trascinare **KaraokeManager.app** in **Applicazioni**
3. **Primo avvio** (app non firmata): tasto destro → **Apri** → **Apri**  
   (oppure Impostazioni di sistema → Privacy e sicurezza → Apri comunque)

## Dove finiscono i dati

```
~/Library/Application Support/KaraokeManager/
├── data/karaoke.db
├── media/downloads/          # karaoke YouTube
├── media/dj/downloads/       # brani DJ
└── logs/karaoke_manager.log
```

Il `.app` in `/Applications` resta immutabile; aggiornare l'app non cancella libreria e database.

## Universal2 — note pratiche

Per un `.dmg` che gira **sia su Intel che su M1**:

| Componente | Requisito |
|------------|-----------|
| Python | Installer universal2 da python.org |
| PyQt6 / PyInstaller | Installati con quel Python |
| VLC.app | Il build ufficiale VideoLAN è di solito universal2 |
| ffmpeg | `brew install ffmpeg` su Mac Apple Silicon produce spesso binario arm64; su Intel, x86_64 |

Se lo script segnala che un componente non è universal2:

- **Opzione A:** buildare su ciascun Mac con `./build/build_macos.sh arm64` o `x86_64` e distribuire due `.dmg`
- **Opzione B:** installare Python universal2 + ffmpeg fat (`brew` su Mac Intel per x86_64, verificare con `lipo -archs $(which ffmpeg)`)

Verifica architetture:

```bash
lipo -archs dist/KaraokeManager.app/Contents/MacOS/KaraokeManager
lipo -archs dist/KaraokeManager.app/Contents/MacOS/vlc/libvlc.dylib
lipo -archs dist/KaraokeManager.app/Contents/MacOS/bin/ffmpeg
```

Output atteso per universal2: `x86_64 arm64`

## Risoluzione problemi

| Problema | Azione |
|----------|--------|
| Gatekeeper blocca l'app | Tasto destro → Apri (prima volta) |
| Video nero | Verificare che `vlc/plugins` sia nel bundle; controllare `logs/karaoke_manager.log` |
| yt-dlp / SSL | `certifi` incluso; verificare connessione rete |
| Build PyInstaller fallisce su universal2 | Riprovare con `./build/build_macos.sh native` o arch specifica |

## Firma (futuro)

File preparato: `build/entitlements.plist`. Con Apple Developer account si potranno aggiungere `codesign` e `notarytool` allo script.
