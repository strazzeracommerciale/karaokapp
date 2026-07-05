"""Confronto versioni semver-like (2.0, 2.0.1, v2.1)."""

from __future__ import annotations

import re


def normalize_version_label(raw: str) -> str:
    """Rimuove prefisso 'v' e spazi dal tag release."""
    return (raw or "").strip().lstrip("vV")


def version_tuple(raw: str) -> tuple[int, ...]:
    """Converte una stringa versione in tupla numerica per il confronto."""
    label = normalize_version_label(raw)
    parts: list[int] = []
    for piece in re.split(r"[.\-+]", label):
        if piece.isdigit():
            parts.append(int(piece))
        elif parts:
            break
    return tuple(parts) if parts else (0,)


def is_newer_version(remote: str, current: str) -> bool:
    """True se `remote` è più recente di `current`."""
    return version_tuple(remote) > version_tuple(current)
