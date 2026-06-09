# Pitch Shift — Roadmap futura

## Scope
Solo modalità karaoke. Non applicabile alla modalità DJ.

## Approccio validato (da implementare)
Pre-processing a monte: il file viene processato con pedalboard
PRIMA di essere passato a VLC, non durante la riproduzione.
VLC riceve un file già con il pitch corretto — trasparente per lui.

## Flusso target
1. Cantante aggiunto in coda con pitch_offset impostato
2. DownloadService/AudioEngine processa il file in background (QThread)
3. File processato salvato in TEMP_DIR con prefisso km_proc_
4. Al momento della riproduzione, PlayerService usa il file processato
5. Cleanup del temp file a fine brano

## Vincolo noto
Non gestisce cambi di tonalità last-minute durante la riproduzione.
Accettato: meglio pitch pre-impostato che nessun pitch.

## Regola di sviluppo
Implementare in sandbox isolata (branch o cartella separata).
Test completo prima di integrare nel programma principale.
Se il test fallisce: si butta via tutto senza aver toccato nulla.

## Prerequisiti tecnici già verificati
- pedalboard funziona su Python 3.13 Windows (testato)
- ffmpeg estrae audio WAV da MP4 correttamente (testato)
- Il processing su file da 70MB richiede ~20-30 secondi (accettabile
  se fatto in background durante la serata mentre altri cantano)
- pyrubberband NON usare: bug con path Windows abbreviati (FABREM~1)
