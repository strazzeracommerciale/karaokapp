"""Gestione temi UI (chiaro A / scuro B) con persistenza QSettings."""

import logging
from typing import Literal

from PyQt6.QtCore import QSettings, QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

import config

logger = logging.getLogger(__name__)

ThemeId = Literal["light", "dark"]

_THEME_FILES: dict[ThemeId, str] = {
    "light": "style_a.qss",
    "dark": "style_b.qss",
}


def load_stylesheet(theme: ThemeId) -> str:
    """Restituisce il contenuto QSS per il tema indicato."""
    filename = _THEME_FILES.get(theme, _THEME_FILES[config.UI_THEME_DEFAULT])
    path = config.ASSETS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    fallback = config.ASSETS_DIR / "style.qss"
    if fallback.exists():
        logger.warning("QSS %s non trovato, fallback su style.qss", filename)
        return fallback.read_text(encoding="utf-8")
    logger.error("Nessun foglio di stile trovato per tema %s", theme)
    return ""


class ThemeService(QObject):
    """Carica e applica il foglio di stile selezionato a tutta l'applicazione."""

    theme_changed = pyqtSignal(str)

    def __init__(self) -> None:
        """Ripristina il tema salvato o il default (scuro B)."""
        super().__init__()
        self._settings = QSettings(config.APP_NAME, config.APP_NAME)
        saved = self._settings.value(config.UI_THEME_SETTINGS_KEY, config.UI_THEME_DEFAULT)
        self._theme: ThemeId = saved if saved in _THEME_FILES else config.UI_THEME_DEFAULT  # type: ignore[assignment]

    def current_theme(self) -> ThemeId:
        """Restituisce l'identificatore del tema attivo."""
        return self._theme

    def set_theme(self, theme: ThemeId) -> None:
        """Passa al tema richiesto, lo persiste e lo applica."""
        if theme not in _THEME_FILES or theme == self._theme:
            return
        self._theme = theme
        self._settings.setValue(config.UI_THEME_SETTINGS_KEY, theme)
        self.apply_globally()
        self.theme_changed.emit(theme)
        logger.info("Tema UI: %s", theme)

    def apply_globally(self) -> None:
        """Applica il QSS corrente a QApplication (tutte le finestre)."""
        app = QApplication.instance()
        if app is None:
            return
        app.setStyleSheet(load_stylesheet(self._theme))
