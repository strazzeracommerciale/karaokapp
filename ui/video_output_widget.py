"""Widget nero per embed nativo dell'output video VLC."""

from collections.abc import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget


class VideoOutputWidget(QWidget):
    """Area video con riaggancio VLC debounced al resize."""

    _VLC_RESIZE_DEBOUNCE_MS = 150

    def __init__(self, *, min_height: int = 200) -> None:
        """Inizializza l'area video."""
        super().__init__()
        self.setMinimumHeight(min_height)
        self.setStyleSheet("background-color: #000000;")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._vlc_resize_callback: Callable[[QWidget], None] | None = None
        self._last_vlc_size = (0, 0)
        self._vlc_resize_timer = QTimer(self)
        self._vlc_resize_timer.setSingleShot(True)
        self._vlc_resize_timer.setInterval(self._VLC_RESIZE_DEBOUNCE_MS)
        self._vlc_resize_timer.timeout.connect(self._emit_vlc_resize)

    def set_vlc_resize_callback(
        self, callback: Callable[[QWidget], None] | None
    ) -> None:
        """Registra callback per riallineare l'HWND VLC dopo un resize del widget."""
        self._vlc_resize_callback = callback
        self._last_vlc_size = (0, 0)

    def resizeEvent(self, event) -> None:
        """Pianifica il riaggancio VLC (debounced) per evitare tempeste di set_hwnd."""
        super().resizeEvent(event)
        if self._vlc_resize_callback is not None and self.width() > 0 and self.height() > 0:
            self._vlc_resize_timer.start()

    def _emit_vlc_resize(self) -> None:
        """Riaggancia VLC solo se le dimensioni sono cambiate in modo significativo."""
        if self._vlc_resize_callback is None:
            return
        size = (self.width(), self.height())
        if size[0] <= 0 or size[1] <= 0:
            return
        last_w, last_h = self._last_vlc_size
        if abs(size[0] - last_w) < 4 and abs(size[1] - last_h) < 4:
            return
        self._last_vlc_size = size
        self._vlc_resize_callback(self)
