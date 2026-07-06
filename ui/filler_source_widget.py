"""Widget selezione sorgente sottofondo: file, brano DJ o playlist DJ."""



from PyQt6.QtCore import Qt, pyqtSignal

from PyQt6.QtGui import QResizeEvent

from PyQt6.QtWidgets import (

    QCheckBox,

    QComboBox,

    QHBoxLayout,

    QLabel,

    QPushButton,

    QSizePolicy,

    QSlider,

    QVBoxLayout,

    QWidget,

)





class FillerSourceWidget(QWidget):

    """Controlli unificati per la sorgente del sottofondo."""



    source_mode_changed = pyqtSignal(str)

    choose_requested = pyqtSignal()

    dj_playlist_selected = pyqtSignal(int, bool)

    shuffle_toggled = pyqtSignal(bool)

    enabled_toggled = pyqtSignal(bool)

    volume_changed = pyqtSignal(int)



    _MODE_FILE = "file"

    _MODE_DJ_TRACK = "dj_track"

    _MODE_DJ_PLAYLIST = "dj_playlist"



    def __init__(self) -> None:

        """Costruisce la barra controlli sottofondo."""

        super().__init__()

        self._playlists: list[dict] = []

        self._source_full_text = "(nessuno)"

        self._build_ui()

        self._sync_mode_controls()

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)



    def _build_ui(self) -> None:

        """Assembla dropdown, picker, shuffle, attivo e volume."""

        root = QVBoxLayout(self)

        root.setContentsMargins(0, 0, 0, 0)

        root.setSpacing(2)



        controls = QHBoxLayout()

        controls.setContentsMargins(0, 0, 0, 0)

        controls.addWidget(QLabel("Sottofondo:"))



        self._mode_combo = QComboBox()

        self._mode_combo.addItem("File", self._MODE_FILE)

        self._mode_combo.addItem("Brano DJ", self._MODE_DJ_TRACK)

        self._mode_combo.addItem("Playlist DJ", self._MODE_DJ_PLAYLIST)

        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        controls.addWidget(self._mode_combo)



        self._choose_btn = QPushButton("Scegli…")

        self._choose_btn.setObjectName("secondaryButton")

        self._choose_btn.clicked.connect(self.choose_requested.emit)

        controls.addWidget(self._choose_btn)



        self._playlist_combo = QComboBox()

        self._playlist_combo.setMinimumWidth(160)

        self._playlist_combo.currentIndexChanged.connect(self._on_playlist_changed)

        controls.addWidget(self._playlist_combo)



        self._shuffle_check = QCheckBox("Shuffle")

        self._shuffle_check.toggled.connect(self.shuffle_toggled.emit)

        controls.addWidget(self._shuffle_check)



        self._enabled_check = QCheckBox("Attivo nelle pause")

        self._enabled_check.toggled.connect(self.enabled_toggled.emit)

        controls.addWidget(self._enabled_check)



        controls.addWidget(QLabel("Vol"))

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)

        self._volume_slider.setRange(0, 100)

        self._volume_slider.setValue(30)

        self._volume_slider.setMinimumWidth(72)

        self._volume_slider.setMaximumWidth(140)

        self._volume_slider.valueChanged.connect(self.volume_changed.emit)

        controls.addWidget(self._volume_slider, stretch=1)



        root.addLayout(controls)



        source_row = QHBoxLayout()

        source_row.setContentsMargins(0, 0, 0, 0)

        self._source_label = QLabel("(nessuno)")

        self._source_label.setObjectName("mutedLabel")

        self._source_label.setSizePolicy(

            QSizePolicy.Policy.Expanding,

            QSizePolicy.Policy.Preferred,

        )

        source_row.addWidget(self._source_label)

        root.addLayout(source_row)



    def resizeEvent(self, event: QResizeEvent) -> None:

        """Tronca il nome file con ellissi se supera la larghezza disponibile."""

        super().resizeEvent(event)

        self._update_source_label_elided()



    def current_source_mode(self) -> str:

        """Restituisce la modalità sorgente selezionata nel dropdown."""

        return self._mode_combo.currentData()



    def set_source_mode(self, mode: str) -> None:

        """Allinea il dropdown alla modalità sorgente attiva."""

        index = self._mode_combo.findData(mode)

        if index >= 0:

            self._mode_combo.blockSignals(True)

            self._mode_combo.setCurrentIndex(index)

            self._mode_combo.blockSignals(False)

            self._sync_mode_controls()



    def set_source_label(self, label: str) -> None:

        """Aggiorna l'etichetta della sorgente attiva."""

        self._source_full_text = label or "(nessuno)"

        self._source_label.setToolTip(self._source_full_text)

        self._update_source_label_elided()



    def set_shuffle_checked(self, checked: bool) -> None:

        """Allinea la checkbox shuffle senza emettere segnali."""

        self._shuffle_check.blockSignals(True)

        self._shuffle_check.setChecked(checked)

        self._shuffle_check.blockSignals(False)



    def is_shuffle_checked(self) -> bool:

        """True se lo shuffle filler playlist è selezionato."""

        return self._shuffle_check.isChecked()



    def set_enabled_checked(self, checked: bool) -> None:

        """Allinea la checkbox attivo senza emettere segnali."""

        self._enabled_check.blockSignals(True)

        self._enabled_check.setChecked(checked)

        self._enabled_check.blockSignals(False)



    def is_enabled_checked(self) -> bool:

        """True se il sottofondo è marcato attivo."""

        return self._enabled_check.isChecked()



    def volume(self) -> int:

        """Restituisce il volume slider corrente."""

        return self._volume_slider.value()



    def set_dj_playlists(self, playlists: list[dict]) -> None:

        """Popola il combo playlist DJ."""

        current_id = self.current_playlist_id()

        self._playlists = list(playlists)

        self._playlist_combo.blockSignals(True)

        self._playlist_combo.clear()

        for playlist in playlists:

            self._playlist_combo.addItem(playlist["name"], playlist["id"])

        if current_id is not None:

            index = self._playlist_combo.findData(current_id)

            if index >= 0:

                self._playlist_combo.setCurrentIndex(index)

        self._playlist_combo.blockSignals(False)



    def current_playlist_id(self) -> int | None:

        """Restituisce l'id playlist DJ selezionata, se presente."""

        value = self._playlist_combo.currentData()

        return int(value) if value is not None else None



    def _update_source_label_elided(self) -> None:

        """Mostra il nome sorgente troncato per non spostare i controlli."""

        width = self._source_label.width()

        if width <= 0:

            width = max(self.width() - 8, 100)

        metrics = self._source_label.fontMetrics()

        elided = metrics.elidedText(

            self._source_full_text,

            Qt.TextElideMode.ElideMiddle,

            width,

        )

        self._source_label.setText(elided)



    def _on_mode_changed(self, _index: int) -> None:

        """Propaga il cambio modalità e aggiorna i controlli visibili."""

        self._sync_mode_controls()

        self.source_mode_changed.emit(self.current_source_mode())



    def _on_playlist_changed(self, _index: int) -> None:

        """Propaga la selezione playlist DJ con lo shuffle corrente."""

        if self.current_source_mode() != self._MODE_DJ_PLAYLIST:

            return

        playlist_id = self.current_playlist_id()

        if playlist_id is not None:

            self.dj_playlist_selected.emit(playlist_id, self.is_shuffle_checked())



    def _sync_mode_controls(self) -> None:

        """Mostra Scegli o combo playlist a seconda della modalità."""

        mode = self.current_source_mode()

        is_playlist = mode == self._MODE_DJ_PLAYLIST

        is_picker = mode in (self._MODE_FILE, self._MODE_DJ_TRACK)

        self._choose_btn.setVisible(is_picker)

        self._playlist_combo.setVisible(is_playlist)

        self._shuffle_check.setVisible(is_playlist)


