# Installare KaraokeManager su Mac

Guida passo passo per scaricare il programma da GitHub e installarlo.
**Non serve installare Python, VLC o ffmpeg.**

---

## Quale file scaricare?

| Il tuo Mac | Artifact da scaricare |
|------------|------------------------|
| **Apple Silicon** (M1, M2, M3…) | `KaraokeManager-macos-arm64` |
| **Intel** (MacBook pre-2020, iMac Intel…) | `KaraokeManager-macos-x86_64` |

Per capire il processore: **Menu Apple** → **Informazioni su questo Mac** → voce **Chip** o **Processore**.

---

## Passo 1 — Apri GitHub Actions

1. Apri il browser (Safari, Chrome, …)
2. Vai a: **https://github.com/strazzeracommerciale/karokapp/actions**
3. Accedi con il tuo account GitHub (se richiesto)

---

## Passo 2 — Scegli l’ultima build riuscita

1. Nella colonna sinistra clicca **Build macOS**
2. Clicca sulla riga in alto con **✓ verde** (ultima esecuzione completata)
3. Se tutte le build sono rosse, apri l’ultima esecuzione e controlla l’errore, oppure attendi che finisca una build in corso (icona gialla)

> **Build manuale:** tab **Actions** → **Build macOS** → pulsante **Run workflow** → **Run workflow**. Attendi 15–25 minuti.

---

## Passo 3 — Scarica il pacchetto

1. Scorri in basso fino alla sezione **Artifacts**
2. Clicca su:
   - **KaraokeManager-macos-arm64** (Mac M1/M2/M3), oppure
   - **KaraokeManager-macos-x86_64** (Mac Intel)
3. Si scarica un file **`.zip`** (es. `KaraokeManager-macos-arm64.zip`)

---

## Passo 4 — Estrai il .dmg

1. Apri **Download** (Finder → Download)
2. **Doppio click** sul file `.zip` scaricato
3. Compare un file **`.dmg`** (es. `KaraokeManager-1.0.2-macOS-arm64.dmg`)

---

## Passo 5 — Installa in Applicazioni

1. **Doppio click** sul file `.dmg`
2. Si apre una finestra con **KaraokeManager.app** e la cartella **Applicazioni**
3. **Trascina** `KaraokeManager.app` su **Applicazioni**
4. Chiudi la finestra del disco e (se compare) clicca **Espelli**

---

## Passo 6 — Primo avvio (obbligatorio)

L’app non è firmata da Apple (uso interno). Al primo avvio:

1. Apri **Finder** → **Applicazioni**
2. **Tasto destro** (o Ctrl+click) su **KaraokeManager**
3. Clicca **Apri**
4. Nella finestra di avviso clicca di nuovo **Apri**

Dopo questa procedura puoi avviare l’app con un normale doppio click.

**Alternativa:** se compare “Impossibile aprire…”, vai in **Impostazioni di sistema** → **Privacy e sicurezza** → **Apri comunque**.

---

## Passo 7 — Verifica che funzioni

1. Si apre la finestra principale di KaraokeManager
2. I dati (libreria, download, impostazioni) vengono salvati in:
   ```
   ~/Library/Application Support/KaraokeManager/
   ```
   Per aprirla: Finder → menu **Vai** → **Vai alla cartella…** → incolla il percorso sopra → Invio

---

## Aggiornare a una versione nuova

1. Ripeti i passi 1–5 con l’ultima build su GitHub
2. Trascina la nuova `KaraokeManager.app` in **Applicazioni**
3. Quando chiede se sostituire, clicca **Sostituisci**

I tuoi brani e il database **non** vengono cancellati (restano in Application Support).

---

## Problemi comuni

| Problema | Soluzione |
|----------|-----------|
| Non vedo Artifacts | La build non è ancora finita o è fallita; controlla che ci sia ✓ verde |
| “App danneggiata” / bloccata | Tasto destro → Apri (passo 6) |
| Video nero | Controlla `~/Library/Application Support/KaraokeManager/logs/karaoke_manager.log` |
| Scaricato il file sbagliato (arm64 vs Intel) | Scarica l’artifact corretto per il tuo processore |
