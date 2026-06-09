"""Gestione schermi multipli e posizionamento finestra HDMI."""

import logging

from PyQt6.QtGui import QScreen
from PyQt6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)


class DisplayManager:
    """Rileva schermi disponibili e posiziona finestre su output esterni."""

    def get_screens(self) -> list[dict]:
        """Elenca gli schermi con index, nome e flag primario."""
        app = QApplication.instance()
        if app is None:
            return []
        screens: list[dict] = []
        for index, screen in enumerate(app.screens()):
            screens.append(
                {
                    "index": index,
                    "name": screen.name(),
                    "is_primary": screen == app.primaryScreen(),
                }
            )
        return screens

    def get_external_screen(self) -> QScreen | None:
        """Restituisce il primo schermo non primario, o None."""
        app = QApplication.instance()
        if app is None:
            return None
        primary = app.primaryScreen()
        for screen in app.screens():
            if screen != primary:
                return screen
        return None

    def has_external_screen(self) -> bool:
        """True se è collegato almeno un secondo schermo oltre al primario."""
        return self.get_external_screen() is not None

    def fullscreen_on(self, window: QWidget, screen: QScreen) -> None:
        """Porta la finestra a schermo intero sullo schermo indicato.

        Su Windows `showFullScreen()` usa lo schermo su cui la finestra si trova in
        quel momento. Per evitare che la finestra finisca sul primario, la si porta
        prima in stato normale, la si posiziona dentro la geometria dello schermo
        bersaglio (così l'handle nativo viene associato a quello schermo) e solo
        dopo si passa a schermo intero.
        """
        window.setGeometry(screen.geometry())
        window.showNormal()
        handle = window.windowHandle()
        if handle is not None:
            handle.setScreen(screen)
        window.setGeometry(screen.geometry())
        window.showFullScreen()
        logger.debug("Fullscreen su schermo: %s", screen.name())

    def move_window_to_screen(self, window: QWidget, screen_index: int) -> bool:
        """Porta la finestra a schermo intero sullo schermo con l'indice dato."""
        app = QApplication.instance()
        if app is None:
            logger.warning("QApplication non disponibile per move_window_to_screen")
            return False
        screens = app.screens()
        if screen_index < 0 or screen_index >= len(screens):
            logger.warning("Indice schermo non valido: %s", screen_index)
            return False
        self.fullscreen_on(window, screens[screen_index])
        return True

    def set_fullscreen_external(self, window: QWidget) -> bool:
        """Mostra la finestra a schermo intero sullo schermo esterno.

        Non ricade mai sul primario: se non c'è un secondo schermo restituisce
        False senza mostrare nulla, così il chiamante può annullare l'attivazione.
        """
        external = self.get_external_screen()
        if external is None:
            logger.warning("Nessuno schermo esterno: output esterno non attivato")
            return False
        self.fullscreen_on(window, external)
        return True
