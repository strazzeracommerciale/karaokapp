"""Risoluzione artista/titolo: metadati yt-dlp con fallback al parsing del titolo."""

from utils.text import parse_artist_title


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def resolve_artist_title(
    raw_title: str,
    info: dict | None = None,
    registry: object | None = None,
) -> tuple[str, str]:
    """Restituisce (artista, titolo) preferendo campi strutturati yt-dlp se presenti."""
    parsed_artist, parsed_title = parse_artist_title(raw_title, registry=registry)
    if not info:
        return parsed_artist, parsed_title or _clean(raw_title)

    meta_artist = _clean(info.get("artist"))
    meta_track = _clean(info.get("track"))
    meta_creator = _clean(info.get("creator"))

    if meta_artist and meta_track:
        if registry is not None and hasattr(registry, "register"):
            registry.register(meta_artist, source="download")
        return meta_artist, meta_track

    if meta_artist and parsed_title:
        if registry is not None and hasattr(registry, "register"):
            registry.register(meta_artist, source="download")
        return meta_artist, parsed_title

    if meta_artist and not parsed_artist:
        title = parsed_title or _clean(info.get("title")) or _clean(raw_title)
        if registry is not None and hasattr(registry, "register"):
            registry.register(meta_artist, source="download")
        return meta_artist, title

    if meta_track and parsed_artist:
        if registry is not None and hasattr(registry, "register"):
            registry.register(parsed_artist, source="download")
        return parsed_artist, meta_track

    if meta_creator and meta_track and not meta_artist:
        if registry is not None and hasattr(registry, "register"):
            registry.register(meta_creator, source="download")
        return meta_creator, meta_track

    if parsed_artist and registry is not None and hasattr(registry, "register"):
        registry.register(parsed_artist, source="download")

    return parsed_artist, parsed_title or _clean(raw_title)
