"""Widget controlli player: play/pausa, stop, skip e seek."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class PlayerWidget(QWidget):
    """Controlli play/pause, stop, skip e seek."""

    play_pause_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    skip_clicked = pyqtSignal()
    seek_requested = pyqtSignal(float)
    volume_changed = pyqtSignal(int)
    set_start_here_clicked = pyqtSignal()

    def __init__(self) -> None:
        """Costruisce i controlli del player."""
        super().__init__()
        self._duration = 0.0
        self._seeking = False
        self._build_ui()

    def _build_ui(self) -> None:
        """Assembla layout controlli."""
        layout = QVBoxLayout(self)
        self._title_label = QLabel("Nessun brano in riproduzione")
        layout.addWidget(self._title_label)
        self._progress = QSlider()
        self._progress.setOrientation(Qt.Orientation.Horizontal)
        self._progress.setRange(0, 1000)
        self._progress.sliderPressed.connect(self._on_seek_start)
        self._progress.sliderReleased.connect(self._on_seek)
        layout.addWidget(self._progress)
        controls = QHBoxLayout()
        self._play_btn = QPushButton("Play/Pause")
        self._play_btn.clicked.connect(self.play_pause_clicked.emit)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("secondaryButton")
        self._stop_btn.clicked.connect(self.stop_clicked.emit)
        self._skip_btn = QPushButton("Skip")
        self._skip_btn.clicked.connect(self.skip_clicked.emit)
        self._set_start_btn = QPushButton("Salva inizio")
        self._set_start_btn.setObjectName("secondaryButton")
        self._set_start_btn.setToolTip(
            "Memorizza la posizione attuale come punto di inizio del brano locale "
            "(salta l'intro). Verrà usata automaticamente alle prossime riproduzioni."
        )
        self._set_start_btn.setEnabled(False)
        self._set_start_btn.clicked.connect(self.set_start_here_clicked.emit)
        controls.addWidget(self._play_btn)
        controls.addWidget(self._stop_btn)
        controls.addWidget(self._skip_btn)
        controls.addWidget(self._set_start_btn)
        controls.addWidget(QLabel("Volume"))
        self._volume = QSlider()
        self._volume.setOrientation(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(100)
        self._volume.valueChanged.connect(self.volume_changed.emit)
        controls.addWidget(self._volume)
        layout.addLayout(controls)

    def _on_seek_start(self) -> None:
        """Sospende l'aggiornamento della barra mentre l'utente trascina."""
        self._seeking = True

    def _on_seek(self) -> None:
        """Emette seek in secondi dalla posizione slider."""
        self._seeking = False
        if self._duration > 0:
            ratio = self._progress.value() / self._progress.maximum()
            self.seek_requested.emit(ratio * self._duration)

    def volume(self) -> int:
        """Restituisce il volume corrente impostato (0-100)."""
        return self._volume.value()

    def set_volume_value(self, value: int) -> None:
        """Imposta il valore dello slider volume (emette volume_changed)."""
        self._volume.setValue(max(0, min(100, int(value))))

    def set_track_info(self, title: str, artist: str | None = None) -> None:
        """Aggiorna etichetta brano corrente."""
        artist_part = f" — {artist}" if artist else ""
        self._title_label.setText(f"{title}{artist_part}")

    def set_start_save_enabled(self, enabled: bool) -> None:
        """Abilita il pulsante 'Salva inizio' (solo per brani locali)."""
        self._set_start_btn.setEnabled(bool(enabled))

    def update_position(self, position_sec: float, duration_sec: float) -> None:
        """Aggiorna la barra di progresso (sospesa durante il seek manuale)."""
        self._duration = duration_sec
        if self._seeking:
            return
        if duration_sec > 0:
            self._progress.setValue(int((position_sec / duration_sec) * 1000))

    def reset(self) -> None:
        """Resetta stato visuale del player."""
        self._title_label.setText("Nessun brano in riproduzione")
        self._progress.setValue(0)
        self._set_start_btn.setEnabled(False)
