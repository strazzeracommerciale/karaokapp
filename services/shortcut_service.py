"""Registro scorciatoie da tastiera con persistenza QSettings.

Progettato per essere esteso da una UI di personalizzazione: ogni azione ha un id
stabile (es. preview_toggle) e una sequenza salvata come testo QKeySequence.
"""

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QKeySequence

import config

# Azioni globali: attive anche con focus in QLineEdit (non servono in digitazione).
ACTION_PREVIEW_TOGGLE = "preview_toggle"
ACTION_PREVIEW_EXIT = "preview_exit"

# Playback: solo fuori dai campi di testo (gestite in MainWindow).
ACTION_PLAY_PAUSE = "play_pause"
ACTION_SEEK_FORWARD = "seek_forward"
ACTION_SEEK_BACK = "seek_back"
ACTION_VOLUME_UP = "volume_up"
ACTION_VOLUME_DOWN = "volume_down"

GLOBAL_ACTIONS = frozenset({ACTION_PREVIEW_TOGGLE, ACTION_PREVIEW_EXIT})

_DEFAULT_BINDINGS: dict[str, str] = {
    ACTION_PREVIEW_TOGGLE: "Alt+X",
    ACTION_PREVIEW_EXIT: "Escape",
    ACTION_PLAY_PAUSE: "Space",
    ACTION_SEEK_FORWARD: "Right",
    ACTION_SEEK_BACK: "Left",
    ACTION_VOLUME_UP: "Up",
    ACTION_VOLUME_DOWN: "Down",
}


class ShortcutService:
    """Lettura/scrittura binding tastiera; confronto con QKeyEvent."""

    def __init__(self) -> None:
        self._settings = QSettings(config.APP_NAME, config.APP_NAME)

    def list_actions(self) -> list[str]:
        """Restituisce gli id azione configurabili (per futura UI impostazioni)."""
        return list(_DEFAULT_BINDINGS.keys())

    def binding_text(self, action: str) -> str:
        """Sequenza configurata per l'azione (es. 'Alt+X')."""
        default = _DEFAULT_BINDINGS.get(action, "")
        key = f"shortcuts/{action}"
        value = self._settings.value(key, default)
        return str(value) if value else default

    def set_binding(self, action: str, sequence: str) -> None:
        """Persiste un nuovo binding (chiamata futura da UI impostazioni)."""
        if action not in _DEFAULT_BINDINGS:
            raise ValueError(f"Azione sconosciuta: {action}")
        self._settings.setValue(f"shortcuts/{action}", sequence)

    def reset_binding(self, action: str) -> None:
        """Ripristina il default di fabbrica per un'azione."""
        if action in _DEFAULT_BINDINGS:
            self._settings.setValue(f"shortcuts/{action}", _DEFAULT_BINDINGS[action])

    def match_global(
        self,
        combination,
        *,
        preview_maximized: bool,
    ) -> str | None:
        """Ritorna l'azione globale corrispondente al tasto premuto, se presente."""
        if self._matches(ACTION_PREVIEW_TOGGLE, combination):
            return ACTION_PREVIEW_TOGGLE
        if preview_maximized and self._matches(ACTION_PREVIEW_EXIT, combination):
            return ACTION_PREVIEW_EXIT
        return None

    def match_playback(self, combination) -> str | None:
        """Ritorna l'azione playback corrispondente (solo fuori dai campi testo)."""
        for action in (
            ACTION_PLAY_PAUSE,
            ACTION_SEEK_FORWARD,
            ACTION_SEEK_BACK,
            ACTION_VOLUME_UP,
            ACTION_VOLUME_DOWN,
        ):
            if self._matches(action, combination):
                return action
        return None

    def _matches(self, action: str, combination) -> bool:
        expected = QKeySequence(self.binding_text(action))
        if expected.isEmpty():
            return False
        return expected == QKeySequence(combination)
