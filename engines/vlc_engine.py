"""Wrapper python-vlc per riproduzione media embeddato in widget PyQt6.

Riproduzione nativa: libVLC decodifica e renderizza video+audio direttamente nel
widget (set_hwnd su win32, set_nsobject su macOS, set_xwindow su Linux), con sync
audio/video gestita internamente da VLC. Per il dual-monitor si usa un secondo player
clonato (stessa istanza libvlc) embeddato nella finestra HDMI; l'audio resta su un solo
player per non duplicare il suono verso l'impianto.
"""

import logging
import sys
from collections.abc import Callable

import vlc
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget

import config

logger = logging.getLogger(__name__)


class VlcEngine:
    """Motore di riproduzione basato su libVLC con callback di posizione."""

    def __init__(self, *extra_args: str) -> None:
        """Inizializza l'istanza VLC e il timer di aggiornamento posizione.

        `extra_args` permette opzioni libVLC aggiuntive (es. "--no-video" per un
        player solo-audio usato come sottofondo, così VLC non apre una finestra video).
        """
        self._instance = vlc.Instance("--no-video-title-show", *extra_args)
        self._player = self._instance.media_player_new()
        self._output_widget: QWidget | None = None
        self._position_callback: Callable[[float], None] | None = None
        self._end_callback: Callable[[], None] | None = None
        self._position_timer = QTimer()
        self._position_timer.setInterval(500)
        self._position_timer.timeout.connect(self._emit_position)
        event_manager = self._player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_end_reached)

    def clone(self) -> "VlcEngine":
        """Crea un secondo player VLC dedicato all'output video HDMI.

        Usa una istanza libvlc separata con --no-audio: il secondario
        non può produrre audio per costruzione, indipendentemente da
        load/play/set_hwnd o qualsiasi altra operazione successiva.
        Non condivide l'istanza con il primario per poter avere
        argomenti di inizializzazione diversi.
        """
        secondary = VlcEngine.__new__(VlcEngine)
        secondary._instance = vlc.Instance(
            "--no-video-title-show",
            "--no-audio",
        )
        secondary._player = secondary._instance.media_player_new()
        secondary._output_widget = None
        secondary._position_callback = None
        secondary._end_callback = None
        secondary._position_timer = QTimer()
        secondary._position_timer.setInterval(500)
        return secondary

    def set_output_widget(self, widget: QWidget) -> None:
        """Collega l'output video al widget PyQt6 (per piattaforma)."""
        self._output_widget = widget
        if sys.platform == "darwin" and not widget.isVisible():
            logger.warning(
                "set_output_widget su macOS prima di show(): "
                "rinviato al prossimo ciclo eventi Qt"
            )
            QTimer.singleShot(0, lambda: self._bind_output_widget(widget))
            return
        self._bind_output_widget(widget)

    def _bind_output_widget(self, widget: QWidget) -> None:
        """Esegue il bind nativo HWND/NSObject/XWindow sul widget."""
        if sys.platform == "darwin":
            self._player.set_nsobject(int(widget.winId()))
        elif sys.platform.startswith("linux"):
            self._player.set_xwindow(int(widget.winId()))
        elif sys.platform == "win32":
            self._player.set_hwnd(int(widget.winId()))
        logger.debug("Output VLC collegato al widget")

    def set_position_callback(self, callback: Callable[[float], None] | None) -> None:
        """Registra callback invocata periodicamente con posizione 0.0–1.0."""
        self._position_callback = callback

    def set_end_callback(self, callback: Callable[[], None] | None) -> None:
        """Registra callback invocata al termine naturale del brano."""
        self._end_callback = callback

    def load(self, path_or_url: str, loop: bool = False, start_time: float = 0.0) -> None:
        """Carica un file locale o URL nel player.

        Con `loop=True` libVLC ripete l'input all'infinito (usato dal sottofondo),
        senza bisogno di callback Python cross-thread per il riavvio.
        Con `start_time > 0` la riproduzione parte direttamente da quell'offset in
        secondi (salta l'intro dei file locali), in modo affidabile senza dover
        eseguire una seek manuale subito dopo il play.
        """
        media = self._instance.media_new(path_or_url)
        if loop:
            media.add_option("input-repeat=65535")
        if start_time > 0:
            media.add_option(f"start-time={start_time:.3f}")
        self._player.set_media(media)
        logger.debug(
            "Media caricato: %s (loop=%s, start=%.3f)", path_or_url, loop, start_time
        )

    def play(self) -> None:
        """Avvia la riproduzione e il timer di posizione."""
        self._player.play()
        self._position_timer.start()
        logger.debug("Riproduzione avviata")

    def pause(self) -> None:
        """Mette in pausa la riproduzione."""
        self._player.pause()
        self._position_timer.stop()
        logger.debug("Riproduzione in pausa")

    def stop(self) -> None:
        """Ferma la riproduzione e resetta il timer."""
        self._player.stop()
        self._position_timer.stop()
        logger.debug("Riproduzione fermata")

    def seek(self, seconds: float) -> None:
        """Salta alla posizione indicata in secondi."""
        self._player.set_time(int(seconds * 1000))

    def set_mute(self, mute: bool) -> None:
        """Silenzia o riattiva l'audio di questo player VLC."""
        self._player.audio_set_mute(bool(mute))

    def set_volume(self, volume: int) -> None:
        """Imposta il volume audio di questo player (0-100)."""
        clamped = max(0, min(100, int(volume)))
        self._player.audio_set_volume(clamped)

    def get_position(self) -> float:
        """Restituisce la posizione normalizzata 0.0–1.0."""
        return self._player.get_position()

    def get_time(self) -> int:
        """Restituisce il tempo corrente di riproduzione in millisecondi."""
        return int(self._player.get_time())

    def get_duration(self) -> float:
        """Restituisce la durata in secondi, 0.0 se sconosciuta."""
        length_ms = self._player.get_length()
        if length_ms <= 0:
            return 0.0
        return length_ms / 1000.0

    def is_playing(self) -> bool:
        """True se il player è in stato di riproduzione attiva."""
        return bool(self._player.is_playing())

    def _emit_position(self) -> None:
        """Invoca il callback di posizione con il valore corrente."""
        if self._position_callback is not None:
            self._position_callback(self.get_position())

    def _on_end_reached(self, _event: vlc.Event) -> None:
        """Gestisce la fine naturale del brano."""
        self._position_timer.stop()
        if self._end_callback is not None:
            self._end_callback()
        logger.debug("Playback terminato")
