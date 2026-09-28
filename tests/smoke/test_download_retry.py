"""Un 403 YouTube transitorio non deve essere trattato come errore definitivo."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.download_service import is_retryable_download_error


def test_http_403_is_retryable() -> None:
    message = "ERROR: unable to download video data: HTTP Error 403: Forbidden"
    assert is_retryable_download_error(message)


def test_missing_file_is_not_retryable() -> None:
    assert not is_retryable_download_error("Download non trovato: brano.mp4")


if __name__ == "__main__":
    test_http_403_is_retryable()
    test_missing_file_is_not_retryable()
    print("ok")
