"""Esito refresh metadati per singolo brano."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RefreshStatus = Literal["updated", "renamed", "unchanged", "skipped", "error"]


@dataclass
class TrackRefreshOutcome:
    """Dettaglio elaborazione metadati/rinomina di un brano."""

    track_id: int
    status: RefreshStatus
    old_title: str
    old_artist: str | None
    new_title: str
    new_artist: str | None
    old_path: str
    new_path: str | None = None
    message: str = ""

    @property
    def changed(self) -> bool:
        """True se titolo, artista o percorso file sono cambiati."""
        return self.status in ("updated", "renamed")

    def display_summary(self) -> str:
        """Etichetta breve per liste di revisione."""
        labels = {
            "updated": "Metadati aggiornati",
            "renamed": "File rinominato",
            "unchanged": "Invariato",
            "skipped": "Saltato",
            "error": "Errore",
        }
        base = labels.get(self.status, self.status)
        if self.message:
            return f"{base}: {self.message}"
        return base
