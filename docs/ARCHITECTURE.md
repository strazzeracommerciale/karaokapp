# Architettura KaraokeManager

KaraokeManager è organizzato in **4 layer** con dipendenze unidirezionali:
UI → Service → Engine → Data. Nessun layer inferiore importa da quelli superiori.

## Schema a layer

```
┌─────────────────────────────────────────────────────────────────────┐
│                              UI (PyQt6)                             │
│  main_window  search_widget  queue_widget  hdmi_window              │
│  dj_console_window  dj_runtime_widget  dj_library_widget  ...       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ segnali / chiamate dirette
┌──────────────────────────────▼──────────────────────────────────────┐
│                            SERVICE                                  │
│  player_service  queue_service  library_service  playlist_service   │
│  search_service  download_service  filler_service                   │
│  app_mode_service  karaoke_playback_flow  dj_playback_flow          │
│  dj_runtime_service  external_display_coordinator                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ astrazione su engine e DB
┌──────────────────────────────▼──────────────────────────────────────┐
│                            ENGINE                                   │
│  vlc_engine  ytdlp_engine  search_engine  display_manager             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ SQL / file system
┌──────────────────────────────▼──────────────────────────────────────┐
│                             DATA                                    │
│  db_core  schema.sql  (SQLite: tracks, playlists, sessions, ...)   │
└─────────────────────────────────────────────────────────────────────┘
```

Il punto di ingresso `main.py` costruisce il grafo delle dipendenze, collega i
segnali Qt e avvia il loop eventi. Non contiene logica di dominio.

---

## Moduli principali per layer

### UI (`ui/`)

| Modulo | Ruolo |
|--------|-------|
| `main_window.py` | Finestra principale karaoke: player, coda, ricerca, libreria |
| `search_widget.py` | Ricerca unificata locale + YouTube (karaoke) |
| `queue_widget.py` | Visualizzazione e gestione coda sessione |
| `playlist_widget.py` | CRUD playlist karaoke |
| `library_widget.py` | Catalogo brani karaoke |
| `hdmi_window.py` | Output video su monitor esterno |
| `dj_console_window.py` | Finestra DJ autonoma (tab Runtime / Libreria / Playlist / Ricerca) |
| `dj_runtime_widget.py` | Coda runtime DJ in memoria |
| `dj_library_widget.py` | Import e scan catalogo DJ |
| `dj_playlist_widget.py` | Playlist persistenti DJ |
| `dj_search_widget.py` | Ricerca e download YouTube DJ |

### Service (`services/`)

| Modulo | Ruolo |
|--------|-------|
| `player_service.py` | Riproduzione VLC primario + secondario, segnali track |
| `queue_service.py` | Coda karaoke per sessione corrente |
| `library_service.py` | Catalogo brani, import/scan, filtro `track_type` |
| `playlist_service.py` | Playlist persistenti con validazione `mode` |
| `search_service.py` | Ricerca asincrona (worker Qt), trigger download |
| `download_service.py` | Download yt-dlp in background |
| `filler_service.py` | Sottofondo automatico tra i brani karaoke |
| `app_mode_service.py` | Stato condiviso modalità `karaoke` / `dj` |
| `karaoke_playback_flow.py` | Flow controller comandi playback karaoke |
| `dj_playback_flow.py` | Flow controller comandi playback DJ |
| `dj_runtime_service.py` | Runtime DJ in memoria (shuffle, loop, coda) |
| `external_display_coordinator.py` | Coordinamento dual monitor e HDMI |

### Engine (`engines/`)

| Modulo | Ruolo |
|--------|-------|
| `vlc_engine.py` | Wrapper python-vlc, clone istanza secondaria |
| `ytdlp_engine.py` | Download e conversione media da YouTube |
| `search_engine.py` | Ricerca fuzzy locale + query YouTube per `track_type` |
| `display_manager.py` | Enumerazione schermi disponibili |

### Data (`db/`)

| Modulo | Ruolo |
|--------|-------|
| `db_core.py` | Connessione SQLite, migrazioni, backup |
| `schema.sql` | Schema: `tracks`, `playlists`, `playlist_tracks`, `sessions`, … |

---

## Decisioni architetturali

### Dual monitor — VLC secondario `--no-audio`

Il player usa due istanze VLC clonate da `vlc_engine.clone()`:

- **Primario**: audio + video nel widget principale (`MainWindow`)
- **Secondario**: solo video su `HdmiWindow`, avviato con argomento `--no-audio`

Il secondario non usa `set_mute()`: il silenzio è garantito a livello di istanza VLC,
non tramite controllo runtime del volume. Evita conflitti con il player principale.

### Database unico con `track_type`

Un solo file SQLite (`data/karaoke.db`) per karaoke e DJ. La colonna `track_type`
(`'karaoke'` | `'dj'`) separa i cataloghi a livello di query. Stesso path fisico
può esistere come entrambi i tipi; le playlist validano `mode` ↔ `track_type`.

### Finestra DJ separata

`DjConsoleWindow` è una finestra autonoma (`Qt.Window`), non un pannello di
`MainWindow`. Il toggle avviene in `main.py` via segnale `dj_console_toggle_requested`
(show/hide). La geometria è persistita in `QSettings`.

### Flow controller separati

`KaraokePlaybackFlow` e `DjPlaybackFlow` sono controller distinti. Entrambi
ricevono gli eventi player, ma agiscono solo quando `AppModeService.get_mode()`
corrisponde. Questo evita accoppiamento tra coda karaoke e runtime DJ.

### `AppModeService` condiviso

Un'unica istanza di `AppModeService` è iniettata in `MainWindow`, `DjConsoleWindow`
e nei flow controller. Il cambio modalità propaga `mode_changed` a tutti i
consumatori (pill UI, abilitazione controlli player, guard nei flow).

---

## Bootstrap (`main.py`)

Ordine di avvio:

1. Migrazione DB + servizi core (senza player VLC)
2. `MainWindow` + `HdmiWindow` + coordinatori
3. Engine VLC/yt-dlp + `SearchService` karaoke e DJ (download condiviso)
4. `DjConsoleWindow` con tutte le dipendenze
5. Wiring segnali, `set_player`, `show()`, inizializzazione HDMI

In modalità `--dry-run` VLC è disabilitato; `_DryRunDownloadService` espone gli
stessi segnali Qt di `DownloadService` per compatibilità con la consolle DJ.
