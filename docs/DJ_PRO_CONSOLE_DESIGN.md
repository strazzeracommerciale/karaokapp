# KaraokeManager — Fase 5: Consolle DJ Pro

Documento di progetto (bozza per revisione congiunta).
Integra l'analisi codebase di due passaggi indipendenti.

**Scope:** dual deck, crossfader software, pre-ascolto cuffie, controller MIDI Numark Party Mix II.

**Non scope (v1):** scratch vero, beatmatching/BPM sync, effetti/pads sampler, pitch shift DJ live.

---

## 0. Prerequisito bloccante — verifica hardware

Prima di finalizzare l'implementazione audio, eseguire test con Party Mix II fisico su Windows:

1. Come enumera Windows l'interfaccia USB? (endpoint 4ch singolo vs due endpoint stereo)
2. Quali device ID restituisce `audio_output_device_enum()` di VLC per ciascun endpoint?
3. I canali 3–4 del jack cuffie sono raggiungibili senza mixer software?
4. Sniff MIDI in/out (Mixxx o tool equivalente) per confermare note/CC e messaggi LED

**Fork decisionale:** se il controller espone un solo endpoint 4ch non splittabile, la v1 VLC-only non può garantire routing cuffie indipendente → AudioMixerEngine (Fase 5b) diventa obbligatoria, non opzionale.

---

## 1. Stato attuale (baseline)

### 1.1 Istanze libvlc in runtime

| Istanza | Creazione | Audio | Video | Ruolo |
|---------|-----------|-------|-------|-------|
| `vlc_engine` | `VlcEngine()` | Sì | MainWindow | Karaoke + DJ sequenziale |
| `vlc_engine_secondary` | `clone()` + `--no-audio` | No | HdmiWindow | Mirror HDMI del primario |
| `filler_engine` | `VlcEngine(*FILLER_VLC_ARGS)` | Sì (DirectSound su Win) | No | Sottofondo |

Precedente utile: il filler usa già `--aout=directsound` su Windows per **sessione audio separata** dal karaoke WASAPI (`config.py`).

### 1.2 Componenti playback DJ oggi

- **`PlayerService`**: modello single-track. Un brano, un volume, primario+HDMI sincronizzati. Condiviso karaoke/DJ.
- **`DjPlaybackFlow`**: flow sequenziale auto-advance. Legge `DjRuntimeService`, chiama `PlayerService.play_track()`. Ownership `_dj_owns_playback` ≠ modalità attiva.
- **`FillerService`**: player audio indipendente, fade timer (50 ms step), sorgenti file/brano DJ/playlist DJ, crossfade 800 ms tra brani playlist.
- **`DjRuntimeService`**: coda in memoria, shuffle/loop Fisher-Yates — sorgente tracce, non semantica A/B.

### 1.3 Riutilizzabile vs da sostituire

| Riutilizzabile | Non riutilizzabile as-is |
|----------------|--------------------------|
| `VlcEngine` wrapper (volume, seek, end-callback, extra-args) | Modello single-track di `PlayerService` |
| Pattern fade `FillerService` → estrarre `VolumeFader` | `DjPlaybackFlow` → path `PlayerService` |
| `DjRuntimeService`, libreria/playlist/search DJ | `vlc_engine_secondary` come deck B |
| `DjConsoleWindow` come shell UI | Routing audio attuale (mono program) |
| `AppModeService`, pattern ownership | — |

---

## 2. Architettura target

### 2.1 Principio guida

**Non estendere `PlayerService` per il dual deck.** Resta il cuore karaoke (un brano, dual monitor, ownership con i flow karaoke). Il DJ pro introduce un sottosistema parallelo.

```
UI (DjConsoleWindow — tab Mixer / deck A / deck B)
    │
    ├── DjMixerFlow          ← comandi manuali pro (UI + MIDI)
    └── DjPlaybackFlow       ← auto-DJ serata (evolve, non si elimina)
            │
            ▼
    DjMixerService           ← crossfader, master, curve gain
            │
    ┌───────┴───────┐
    ▼               ▼
DeckService A    DeckService B     (o DjDeckService con param deck_id)
    │               │
    ▼               ▼
VlcEngine A      VlcEngine B       (istanze libvlc separate)
            │
            ▼
    AudioRoutingService          ← profilo dispositivo/canali
            │
    ProgramBus + CueBus
```

Componenti aggiuntivi:

- **`CueService`**: deck in pre-ascolto, mix cuffie (v1 semplificato, vedi §3.3)
- **`VolumeFader`**: utility estratta da `FillerService` (QTimer, curve, callback)
- **`MidiDeviceService`** + **`MidiMappingService`**: I/O grezzo + tabella Party Mix II

### 2.2 Volume e crossfader

Per ogni deck:

```
gain_effettivo = trim_deck × fader_canale × curva_crossfader(xf) × master
```

- **Trim / fader canale**: 0–100, indipendenti per deck
- **Crossfader** `xf ∈ [0, 1]`: curva **equal-power** (`cos/sin`), non lineare
- Applicazione: `DjMixerService` calcola i due gain e chiama `VlcEngine.set_volume()` su ciascun deck

Limitazione VLC: volume intero 0–100 → possibile zipper noise su crossfader veloce; accettabile in v1, mitigabile in v2 con mixer PCM float.

### 2.3 HDMI (`vlc_engine_secondary`)

Con due deck non esiste "il brano corrente" univoco. VLC non fa compositing video.

**v1 consigliata:** in modalità DJ pro, HDMI mostra **schermata idle/info brano** (pattern già in `HdmiWindow`), non video deck.

**v1.1 (evoluzione):** HDMI segue il deck **dominante** al crossfader (hard-cut con isteresi al centro per evitare flicker).

Il secondary resta agganciato a `PlayerService` per il karaoke. `ExternalDisplayCoordinator` decide il contenuto HDMI in base alla modalità attiva e al sottosistema playback owner.

### 2.4 Due modalità DJ coesistenti

| Modalità | Flow | Comportamento |
|----------|------|---------------|
| Auto-DJ (Phase 3) | `DjPlaybackFlow` | Coda runtime, auto-advance, filler a esaurimento |
| Console pro (Phase 5) | `DjMixerFlow` | Due deck manuali, crossfader, cue, MIDI |

Mutua esclusione del **bus audio program**: un arbitro (`ProgramBusOwner` o policy in `AppModeService`) decide chi suona in sala. Con engine separati, karaoke e DJ *potrebbero* tecnicamente suonare insieme — va vietato esplicitamente in v1 salvo policy futura.

### 2.5 Filler

Resta player indipendente. Integrazione solo a livello **policy**:

- Interrupt quando un deck program va in play
- Duck volume (opzionale v1.1) sotto program attivo
- Non partecipa al routing multicanale deck A/B

---

## 3. Audio routing

### 3.1 Scenari target

**A — PC standalone (nessun controller):**
Uscita stereo singola, split didattico: L = deck A, R = deck B.
Utile per prove senza hardware DJ.

**B — Numark Party Mix II:**
Interfaccia USB class-compliant, 4 canali.
Routing DJ corretto (non letterale "deck A = master, deck B = cuffie"):

| Canali USB | Bus | Contenuto |
|------------|-----|-----------|
| 1–2 | Master (RCA controller) | **Program mix** (A+B crossfaded) |
| 3–4 | Headphones (jack controller) | **Cue mix** (deck selezionato pre-ascolto ± program, vedi sotto) |

La formulazione "deck A su master, deck B su cuffie" descrive uno split per-deck semplificato utile in v1 ridotta, ma **non** è il comportamento da consolle DJ professionale.

### 3.2 Enumerazione dispositivi

| Layer | API | Uso |
|-------|-----|-----|
| VLC | `audio_output_device_enum()` + `audio_output_device_set(None, id)` | Assegnazione device per player (mmdevice Win, auhal macOS) |
| PortAudio | `sounddevice.query_devices()` | UI configurazione ricca (canali, hostapi, sample rate) |

`AudioRoutingService` espone:

- `list_output_devices() → list[AudioDeviceInfo]`
- `detect_party_mix() → bool`
- `apply_profile(profile: StandaloneStereo | PartyMixDualEndpoint | PartyMix4ch | Custom)`
- `route_program(deck_a_pcm, deck_b_pcm)` / `route_cue(...)` — no-op in v1 VLC-only

### 3.3 Capacità VLC vs mixer software

| Scenario | VLC nativo | Note |
|----------|------------|------|
| B — due endpoint stereo separati | **Sì** | Deck A → endpoint Master, cue → endpoint Headphones |
| B — endpoint 4ch singolo | **No** | VLC non mappa canali 3–4 |
| A — L/R split su stereo singolo | **Fragile** | Filtro `--audio-filter=remap` per istanza; non runtime, poco testato |
| Cue mix vero (master + pre-fader cue in cuffia) | **No** | Richiede mixing PCM |

### 3.4 Pre-ascolto — definizione per fase

**v1 (VLC per-deck routing):**
- Cue = il deck selezionato suona sull'endpoint cuffie (o device PC dedicato)
- Program = entrambi i deck mixati via gain software sul bus master
- **Non** è cue pre-fader Mixxx-style (ascoltare un deck in cuffia mentre suona già in sala sullo stesso deck)

**v2 (AudioMixerEngine):**
- VLC decodifica via `audio_set_callbacks` → PCM
- `sounddevice` (PortAudio) apre device N-canale, mix float in callback numpy
- Cue mix vero: `headphones = cue_deck × cue_gain + program × cue/master_ratio`

Costo v2: buffering, GIL (mix solo numpy vettoriale nel callback), underrun, latenza — sotto-progetto da prototipare in sandbox (stessa prassi di `PITCH_SHIFT_ROADMAP.md`).

### 3.5 Sessioni audio Windows

Con 5+ player simultanei (karaoke, HDMI muto, filler DirectSound, deck A, deck B):

- Evitare WASAPI condiviso tra istanze con volume indipendente (bug VLC #77925)
- Preferire DirectSound per deck/filler dove possibile, o mixer unificato v2
- Documentare combinazioni testate

---

## 4. MIDI — Numark Party Mix II

### 4.1 Librerie (richiedono approvazione `.cursorrules`)

| Libreria | Ruolo |
|----------|-------|
| `mido` | API messaggi tipizzata |
| `python-rtmidi` | Backend I/O (WinMM / CoreMIDI) |

Scartato: `pygame.midi` (dipendenza pesante, non idiomatico Qt).

### 4.2 Struttura moduli

```
engines/midi_engine.py       → open/close porte, recv/send, nessuna logica Qt
services/midi_service.py     → QObject ponte: callback thread → segnali Qt (queued)
midi_mappings/party_mix_ii.py → tabella (tipo, canale, note/cc) → azione semantica
```

Pattern threading: regola 5.3 `.cursorrules` — callback driver MIDI **non** tocca Qt; `QMetaObject.invokeMethod` o segnali queued verso main thread (come worker download).

### 4.3 Mapping controlli → servizi

| Controllo fisico | Target | Note v1 |
|------------------|--------|---------|
| Play/Pause A/B | `DeckService.play_pause(deck)` | — |
| Cue A/B | `CueService.set_cue_deck(deck)` | — |
| Crossfader | `DjMixerService.set_crossfader(float)` | CC continuo |
| Channel fader A/B | `DeckService.set_fader(deck, float)` | — |
| Jog wheel | `DeckService.nudge(deck, ticks)` | Seek incrementale, non scratch |
| Pitch slider | `DeckService.set_rate(deck, float)` | Cambia pitch (VLC), udibile |
| Sync | stub / no-op | Nessun BPM engine |
| Pads | hot-cue (memorizza/seek posizione) | No sampler/FX |
| Load / skip | `DjRuntimeService` + load su deck libero | — |

Fonte numeri note/CC: reverse-engineer da [MIXXX-Numark-party-mix-2](https://github.com/magtomm/MIXXX-Numark-party-mix-2) + sniff hardware.

MIDI e UI sono **due frontend** dello stesso service layer — zero logica duplicata nei VlcEngine.

### 4.4 Feedback LED

- Aprire porta MIDI **output** accanto all'input
- LED accesi con Note On (stessa nota/canale del pulsante, velocity on/off)
- Tabella output separata da input (evitare loop feedback)
- v1: play state, cue state per deck; pad mode indicator se documentato
- Lightshow party del controller: probabilmente non via MIDI — fuori scope

---

## 5. Piano di implementazione

### Fase 5a — Dual deck VLC + MIDI (condizionata a verifica hardware favorevole)

1. Verifica hardware Party Mix II (§0)
2. Approvazione dipendenze: `mido`, `python-rtmidi`
3. Estrarre `VolumeFader` da `FillerService`
4. `DeckService` ×2 + `DjMixerService` + `CueService` (v1 semplificato)
5. `DjMixerFlow` + UI deck/crossfader in `DjConsoleWindow`
6. `AudioRoutingService` — profilo dual-endpoint se disponibile
7. `MidiDeviceService` + mapping Party Mix II + LED base
8. Policy `ProgramBusOwner` — mutua esclusione karaoke/DJ pro/filler
9. Test mock MIDI + `--dry-run` esteso (stub deck senza VLC)
10. Aggiornare `ARCHITECTURE.md` e regola 7 (nuovi branch piattaforma: audio device ID, MIDI)

### Fase 5b — AudioMixerEngine PCM (se §0 fallisce o per scenario A robusto)

1. Approvazione dipendenza: `sounddevice`
2. Prototipo sandbox: decode callback + mix 4ch + latenza misurata
3. Integrazione sostitutiva del routing v1 VLC-only
4. Cue mix vero

### Evoluzioni post-v1

- HDMI video deck dominante
- BPM detection + sync
- Hot-cue avanzati, loop
- Profili MIDI controller aggiuntivi

---

## 6. Rischi e vincoli

| Gravità | Rischio | Mitigazione |
|---------|---------|-------------|
| **Critica** | Endpoint 4ch singolo → VLC non raggiunge cuffie | Fase 5b obbligatoria; verifica §0 prima di promettere |
| **Critica** | Scenario A L/R split fragile con VLC | Accettare fallback "entrambi su master" in v1, o saltare a 5b |
| **Alta** | Aspettativa cue pre-fader vs v1 per-deck routing | Dichiarare esplicitamente in UI e documentazione |
| **Alta** | VLC non è motore DJ (scratch, beat sync, seek keyframe) | Scope v1 = party DJ karaoke-centrico |
| **Alta** | 5+ sessioni audio Windows | DirectSound per deck; matrice combinazioni testate |
| **Media** | Refactor ownership: karaoke e DJ su engine separati possono co-suonare | `ProgramBusOwner` esplicito |
| **Media** | Cross-thread VLC callbacks × N deck | Pattern unificato: callback → pyqtSignal → main thread |
| **Media** | Volume intero VLC → zipper crossfader | Equal-power + step minimo; PCM in v2 |
| **Bassa** | Repo mapping Mixxx vuoto/minimo | Sniff hardware |
| **Bassa** | macOS + Party Mix II | Test secondari; branching auhal |

---

## 7. Dipendenze da approvare

| Libreria | Fase | Motivo |
|----------|------|--------|
| `mido` | 5a | Mapping MIDI leggibile |
| `python-rtmidi` | 5a | Backend I/O MIDI |
| `sounddevice` | 5b | PortAudio, routing multicanale |

`numpy` già approvato — usato nel mixer PCM v2.

---

## 8. Criteri di accettazione v1

- [ ] Due deck riproducono file DJ indipendentemente (load, play, pause, seek)
- [ ] Crossfader software controlla mix program con curva equal-power
- [ ] Fader canale e trim indipendenti per deck
- [ ] Pre-ascolto funzionante secondo profilo hardware verificato (dual-endpoint minimo)
- [ ] Party Mix II: play/pause, crossfader, fader, cue mappati via MIDI
- [ ] LED play/cue riflettono stato deck
- [ ] Karaoke e DJ pro non suonano in sala contemporaneamente senza policy esplicita
- [ ] Modalità auto-DJ (Phase 3) continua a funzionare
- [ ] Smoke test esistenti verdi; nuovi test per mixer gain curve e mapping MIDI mock

---

*Versione: 0.1 — bozza integrata. Prossimo passo: revisione post-verifica hardware §0.*
