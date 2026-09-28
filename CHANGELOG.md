# Registro versioni

Lavoro sulla copia locale. Ogni versione elenca cosa è stato aggiornato, aggiunto o corretto
rispetto alla precedente. La pubblicazione su GitHub avviene solo quando viene chiesta.

La versione 3.0.1 è la release corrente.

## 3.0.1

- Corretto «Inizia da qui»: il punto di inizio veniva passato a mpv nel campo sbagliato, il caricamento rispondeva «invalid parameter» e il brano non partiva più. Il punto già salvato resta valido.

## 3.0.0

- Aggiornato il motore di riproduzione su Windows: al posto di VLC c'è mpv con Rubber Band. Il tono si cambia a brano partito, un semitono alla volta, da −5 a +5, senza cambiare la velocità. Su macOS resta VLC.
- Aggiunti i pulsanti del tono sotto i controlli del brano karaoke.
- Aggiornato il secondo schermo: il lettore resta acceso quando il monitor si spegne e, alla riaccensione, si aggancia una volta sola alla posizione del brano.
- Corretto il sottofondo: scegliendo il file la musica parte subito, se in quel momento non c'è un brano karaoke in corso.
- Aggiornata la build Windows: il pacchetto include lo stesso mpv provato in ascolto (28 settembre 2026, senza AVX2), più vulkan-1.dll e d3dcompiler_43.dll.

## 2.2.8

- Aggiunta la barra dei menu in alto: File, Visualizza, Aiuto. I pulsanti della serata restano al loro posto.
- Aggiunto in File: Sfoglia libreria, Importa libreria, Esporta libreria, Esci.
- Aggiunto in Visualizza: tema chiaro, tema scuro, monitor esterno, consolle DJ, preparazione.
- Aggiunto in Aiuto: Cerca aggiornamenti e Informazioni, che mostra il numero di versione.
- Aggiornato il riconoscimento di artista e titolo. Il programma non si fida più di un solo formato: cerca il brano nel catalogo iTunes e lo accetta solo se artista e titolo compaiono entrambi nel titolo originale del video. Una prova su 51 brani di canali diversi ha dato artista e brano giusti, senza nomi invertiti e senza tag dei canali. Se il catalogo non conferma, il brano resta senza spunta. Una correzione già confermata a mano non viene sovrascritta.
