# Registro versioni

Lavoro sulla copia locale. Ogni versione elenca cosa è stato aggiornato, aggiunto o corretto
rispetto alla precedente. La pubblicazione su GitHub avviene solo quando viene chiesta.

La versione 2.2.8 è l'ultima pubblicata. Il lavoro in corso è la 3.0.0.

## 3.0.0

- Aggiornato il motore di riproduzione su Windows: al posto di VLC c'è mpv con Rubber Band. Il tono si cambia a brano partito, un semitono alla volta, da −5 a +5, senza cambiare la velocità. Su macOS resta VLC.
- Aggiunti i pulsanti del tono sotto i controlli del brano karaoke.
- Aggiornato il secondo schermo: il lettore resta acceso quando il monitor si spegne e, alla riaccensione, si aggancia una volta sola alla posizione del brano.
- Corretto il sottofondo: scegliendo il file la musica parte subito, se in quel momento non c'è un brano karaoke in corso.

## 2.2.8

- Aggiunta la barra dei menu in alto: File, Visualizza, Aiuto. I pulsanti della serata restano al loro posto.
- Aggiunto in File: Sfoglia libreria, Importa libreria, Esporta libreria, Esci.
- Aggiunto in Visualizza: tema chiaro, tema scuro, monitor esterno, consolle DJ, preparazione.
- Aggiunto in Aiuto: Cerca aggiornamenti e Informazioni, che mostra il numero di versione.
- Aggiornato il riconoscimento di artista e titolo. Il programma non si fida più di un solo formato: cerca il brano nel catalogo iTunes e lo accetta solo se artista e titolo compaiono entrambi nel titolo originale del video. Una prova su 51 brani di canali diversi ha dato artista e brano giusti, senza nomi invertiti e senza tag dei canali. Se il catalogo non conferma, il brano resta senza spunta. Una correzione già confermata a mano non viene sovrascritta.
