"""Smoke test confronto versioni e update service."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config
from services.update_service import ReleaseInfo, UpdateService, _UpdateCheckWorker
from utils.version_compare import is_newer_version, normalize_version_label, version_tuple


def test_version_compare() -> None:
    assert version_tuple("v2.0") == (2, 0)
    assert is_newer_version("2.1", "2.0")
    assert not is_newer_version("2.0", "2.0.1")
    assert normalize_version_label("v2.0.3") == "2.0.3"


def test_release_info_from_api_payload() -> None:
    worker = _UpdateCheckWorker("owner/repo", "KaraokeManager-Setup.exe", "1.0")
    release = {
        "tag_name": "v2.1",
        "body": "Novità",
        "assets": [
            {
                "name": "KaraokeManager-Setup.exe",
                "browser_download_url": "https://example.com/setup.exe",
                "size": 1024,
            }
        ],
    }
    info = worker._release_to_info(release)
    assert info is not None
    assert info.version == "2.1"
    assert info.download_url.endswith("setup.exe")


def test_skipped_release_not_offered() -> None:
    settings = MagicMock()
    settings.value.side_effect = lambda key, default=None: {
        config.UPDATE_SETTINGS_SKIP_VERSION_KEY: "2.1",
        config.UPDATE_SETTINGS_LAST_CHECK_KEY: 0,
    }.get(key, default)
    service = UpdateService(settings=settings)
    release = ReleaseInfo("2.1", "v2.1", "", "https://x/y.exe", 0)
    up_to_date: list[int] = []
    available: list[ReleaseInfo] = []
    service.up_to_date.connect(lambda: up_to_date.append(1))
    service.update_available.connect(available.append)
    service._on_check_completed(release)
    assert up_to_date == [1]
    assert available == []
    assert service.pending_release() is None


if __name__ == "__main__":
    test_version_compare()
    test_release_info_from_api_payload()
    test_skipped_release_not_offered()
    print("OK")
