"""Finestra fullscreen per output HDMI esterno.

Il video VLC è agganciato nativamente (`set_hwnd`) al widget `_video_output`: questo lo
trasforma in una finestra nativa che resta SEMPRE sopra gli altri widget Qt della stessa
finestra. Per mostrare l'annuncio del prossimo cantante (testo) sopra/al posto del video
si usa quindi una finestra top-level separata (`_AnnouncementOverlay`), che si sovrappone
in modo affidabile alla superficie video e si nasconde quando la riproduzione parte.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from utils.text import clean_title

logger = logging.getLogger(__name__)


class _VideoOutputWidget(QWidget):
    """Widget nero per embed nativo dell'output video VLC su HDMI."""

    def __init__(self) -> None:
        """Inizializza l'area video."""
        super().__init__()
        self.setStyleSheet("background-color: #000000;")


class _AnnouncementOverlay(QWidget):
    """Finestra top-level che mostra l'annuncio del cantante sopra il video."""

    def __init__(self) -> None:
        """Costruisce l'overlay frameless sempre-in-primo-piano."""
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("background-color: #0b0b0f;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 60, 60, 60)
        self._singer = QLabel("")
        self._singer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._singer.setStyleSheet("color: #4aa3ff; font-size: 60px; font-weight: 700;")
        self._title = QLabel("KaraokeManager")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        self._title.setStyleSheet("color: #ffffff; font-size: 84px; font-weight: 800;")
        self._next = QLabel("")
        self._next.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._next.setStyleSheet("color: #9a9aa6; font-size: 34px;")
        layout.addStretch()
        layout.addWidget(self._singer)
        layout.addWidget(self._title)
        layout.addStretch()
        layout.addWidget(self._next)

    def set_current(self, singer_name: str, song: str) -> None:
        """Mostra il cantante in turno e il titolo del brano."""
        self._singer.setText(singer_name or "")
        self._title.setText(song or "")

    def set_idle(self) -> None:
        """Mostra il messaggio di attesa."""
        self._singer.setText("")
        self._title.setText("In attesa del prossimo cantante…")

    def set_next(self, text: str) -> None:
        """Aggiorna la riga del prossimo cantante."""
        self._next.setText(text)


class HdmiWindow(QWidget):
    """Finestra HDMI: video a tutto schermo + overlay di annuncio."""

    def __init__(self) -> None:
        """Costruisce la finestra HDMI."""
        super().__init__()
        self.setWindowTitle("Karaoke HDMI")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("background-color: #000000;")
        self._overlay = _AnnouncementOverlay()
        self._external_active = False
        self._video_mode = False
        self._build_ui()

    def _build_ui(self) -> None:
        """Assembla il layout: la sola area video riempie la finestra."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._video_output = _VideoOutputWidget()
        layout.addWidget(self._video_output)

    def video_output_widget(self) -> QWidget:
        """Restituisce il widget per embed VLC."""
        return self._video_output

    def set_external_active(self, active: bool) -> None:
        """Abilita/disabilita l'output esterno; se spento nasconde subito l'overlay."""
        self._external_active = active
        if not active:
            self._overlay.hide()

    def show_video(self) -> None:
        """Nasconde l'overlay e porta in primo piano la superficie video.

        Imposta la modalità video: finché è attiva, i normali aggiornamenti della
        coda NON ripresentano l'overlay annuncio sopra il video (era la causa dello
        schermo 2 che restava sull'annuncio invece di mostrare il brano). Il
        raise_() forza Windows a ricomporre la superficie VLC dopo che l'overlay,
        rimasto a lungo in primo piano, l'aveva coperta.
        """
        self._video_mode = True
        self._overlay.hide()
        if self._external_active and self.isVisible():
            self.raise_()
            self._video_output.raise_()

    def announce(self, singer_name: str, title: str, artist: str | None = None) -> None:
        """Forza la modalità annuncio e mostra cantante + brano sullo schermo esterno.

        Chiamato esplicitamente da 'prossimo cantante' (segnale next_ready), così
        l'annuncio compare anche se prima era in corso un video.
        """
        self._video_mode = False
        self.update_current(singer_name, title, artist)

    def _target_geometry(self):
        """Geometria su cui posizionare l'overlay (lo schermo della finestra HDMI)."""
        if self.isVisible():
            return self.geometry()
        primary = QGuiApplication.primaryScreen()
        for screen in QGuiApplication.screens():
            if screen != primary:
                return screen.geometry()
        return primary.geometry() if primary else self.geometry()

    def _show_overlay(self) -> None:
        """Posiziona e mostra l'overlay sopra il video.

        Non fa nulla se l'esterno è spento o se è in corso un video (modalità
        video): evita che un aggiornamento della coda ricopra il brano in onda.
        """
        if not self._external_active or self._video_mode:
            return
        self._overlay.setGeometry(self._target_geometry())
        self._overlay.show()
        self._overlay.raise_()

    def update_current(self, singer_name: str, title: str, artist: str | None = None) -> None:
        """Annuncia cantante e brano sullo schermo esterno (senza avviare il video)."""
        self._overlay.set_current(singer_name, clean_title(title))
        self._show_overlay()

    def update_next(self, queue: list[dict]) -> None:
        """Mostra il prossimo cantante in attesa."""
        waiting = [item for item in queue if item.get("status") == "waiting"]
        if waiting:
            next_item = waiting[0]
            song = clean_title(next_item.get("title", ""))
            self._overlay.set_next(f"Prossimo: {next_item.get('singer_name', '')} — {song}")
        else:
            self._overlay.set_next("")

    def show_idle(self) -> None:
        """Mostra la schermata di attesa sull'overlay."""
        self._video_mode = False
        self._overlay.set_idle()
        self._show_overlay()

    def moveEvent(self, event) -> None:
        """Mantiene l'overlay allineato alla finestra HDMI."""
        if self._overlay.isVisible():
            self._overlay.setGeometry(self.geometry())
        super().moveEvent(event)

    def resizeEvent(self, event) -> None:
        """Mantiene l'overlay allineato quando la finestra cambia dimensione."""
        if self._overlay.isVisible():
            self._overlay.setGeometry(self.geometry())
        super().resizeEvent(event)

    def closeEvent(self, event) -> None:
        """Chiude anche l'overlay con la finestra HDMI."""
        self._overlay.close()
        super().closeEvent(event)
