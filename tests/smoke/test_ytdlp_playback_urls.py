"""Selezione URL di riproduzione quando YouTube separa audio e video."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engines.ytdlp_engine import playback_urls_from_info


def test_progressive_file_has_no_separate_audio() -> None:
    """Un mp4 unico restituisce solo l'URL video."""
    video, audio = playback_urls_from_info({"url": "https://example/video.mp4"})
    assert video == "https://example/video.mp4"
    assert audio is None


def test_separate_streams_return_video_and_audio() -> None:
    """Video H.264 e audio m4a restano due URL da riprodurre insieme."""
    video, audio = playback_urls_from_info(
        {
            "requested_formats": [
                {"url": "https://example/v.mp4", "vcodec": "avc1.4d401e", "acodec": "none"},
                {"url": "https://example/a.m4a", "vcodec": "none", "acodec": "mp4a.40.2"},
            ]
        }
    )
    assert video == "https://example/v.mp4"
    assert audio == "https://example/a.m4a"


def test_missing_url_raises() -> None:
    """Senza URL non c'è nulla da riprodurre."""
    try:
        playback_urls_from_info({})
    except ValueError:
        return
    raise AssertionError("attesa ValueError")


if __name__ == "__main__":
    test_progressive_file_has_no_separate_audio()
    test_separate_streams_return_video_and_audio()
    test_missing_url_raises()
    print("ok")
