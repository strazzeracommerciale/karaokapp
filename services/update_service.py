"""Verifica e installazione aggiornamenti da GitHub Releases (Windows standalone)."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QThread, QTimer, pyqtSignal

import config
from utils.version_compare import is_newer_version, normalize_version_label

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReleaseInfo:
    """Metadati di un aggiornamento disponibile."""

    version: str
    tag: str
    notes: str
    download_url: str
    download_size: int


def update_client_enabled() -> bool:
    """Aggiornamenti online solo su installazione Windows PyInstaller."""
    return sys.platform == "win32" and getattr(sys, "frozen", False)


class _UpdateCheckWorker(QThread):
    """Interroga l'API GitHub Releases in background."""

    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, repo: str, asset_name: str, current_version: str) -> None:
        super().__init__()
        self._repo = repo
        self._asset_name = asset_name
        self._current_version = current_version

    def run(self) -> None:
        try:
            release = self._fetch_latest_release()
            if release is None:
                self.completed.emit(None)
                return
            info = self._release_to_info(release)
            if info is None:
                self.completed.emit(None)
                return
            if not is_newer_version(info.version, self._current_version):
                self.completed.emit(None)
                return
            self.completed.emit(info)
        except Exception as exc:  # noqa: BLE001 - propagato alla UI
            logger.exception("Controllo aggiornamenti fallito")
            self.failed.emit(str(exc))

    def _api_request(self, url: str) -> dict | list:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": config.UPDATE_USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _fetch_latest_release(self) -> dict | None:
        url = f"https://api.github.com/repos/{self._repo}/releases/latest"
        try:
            data = self._api_request(url)
            return data if isinstance(data, dict) else None
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        releases = self._api_request(
            f"https://api.github.com/repos/{self._repo}/releases"
        )
        if not isinstance(releases, list):
            return None
        for release in releases:
            if isinstance(release, dict) and not release.get("draft"):
                return release
        return None

    def _release_to_info(self, release: dict) -> ReleaseInfo | None:
        tag = str(release.get("tag_name") or "")
        version = normalize_version_label(tag)
        assets = release.get("assets") or []
        download_url = ""
        download_size = 0
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            if asset.get("name") == self._asset_name:
                download_url = str(asset.get("browser_download_url") or "")
                download_size = int(asset.get("size") or 0)
                break
        if not download_url:
            logger.warning(
                "Release %s senza asset %r", tag, self._asset_name
            )
            return None
        notes = str(release.get("body") or release.get("name") or "").strip()
        return ReleaseInfo(
            version=version,
            tag=tag,
            notes=notes,
            download_url=download_url,
            download_size=download_size,
        )


class _UpdateDownloadWorker(QThread):
    """Scarica l'installer in background."""

    progress = pyqtSignal(int)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, release: ReleaseInfo, destination: Path) -> None:
        super().__init__()
        self._release = release
        self._destination = destination

    def run(self) -> None:
        try:
            request = urllib.request.Request(
                self._release.download_url,
                headers={"User-Agent": config.UPDATE_USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=300) as response:
                total = int(response.headers.get("Content-Length") or 0)
                if total <= 0:
                    total = self._release.download_size
                self._destination.parent.mkdir(parents=True, exist_ok=True)
                downloaded = 0
                chunk_size = 256 * 1024
                with self._destination.open("wb") as handle:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            percent = min(100, int(downloaded * 100 / total))
                            self.progress.emit(percent)
                self.progress.emit(100)
            self.completed.emit(str(self._destination))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Download aggiornamento fallito")
            self.failed.emit(str(exc))


class UpdateService(QObject):
    """Coordina controllo, download e avvio installer Inno Setup."""

    update_available = pyqtSignal(object)
    check_failed = pyqtSignal(str)
    download_progress = pyqtSignal(int)
    download_completed = pyqtSignal(str)
    download_failed = pyqtSignal(str)
    up_to_date = pyqtSignal()

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self._settings = settings or QSettings(config.APP_NAME, config.APP_NAME)
        self._check_worker: _UpdateCheckWorker | None = None
        self._download_worker: _UpdateDownloadWorker | None = None
        self._pending_release: ReleaseInfo | None = None
        self._auto_apply_after_check = False
        self._busy = False

    @property
    def is_busy(self) -> bool:
        return self._busy

    def pending_release(self) -> ReleaseInfo | None:
        """Release in attesa di installazione con un click."""
        return self._pending_release

    def schedule_startup_check(self) -> None:
        """Controlla aggiornamenti poco dopo l'avvio (con cooldown)."""
        if not update_client_enabled():
            return
        if self._is_on_cooldown():
            return
        if self._is_skipped_version_pending():
            return
        QTimer.singleShot(config.UPDATE_CHECK_DELAY_MS, self.check_for_updates)

    def one_click_update(self) -> None:
        """Un click: usa la release in cache o controlla e applica subito."""
        if self._busy:
            return
        pending = self._pending_release
        if pending is not None and not self._is_skipped(pending.version):
            self.download_update(pending)
            return
        self._auto_apply_after_check = True
        self.check_for_updates(manual=True)

    def check_for_updates(self, *, manual: bool = False) -> None:
        """Avvia il controllo remoto."""
        if self._busy:
            return
        if not manual and self._is_on_cooldown():
            return
        self._busy = True
        self._touch_last_check()
        self._check_worker = _UpdateCheckWorker(
            config.UPDATE_GITHUB_REPO,
            config.UPDATE_INSTALLER_ASSET,
            config.APP_VERSION,
        )
        self._check_worker.completed.connect(self._on_check_completed)
        self._check_worker.failed.connect(self._on_check_failed)
        self._check_worker.finished.connect(self._clear_check_worker)
        self._check_worker.start()

    def download_update(self, release: ReleaseInfo) -> None:
        """Scarica l'installer della release indicata."""
        if self._busy:
            return
        self._busy = True
        destination = config.TEMP_DIR / config.UPDATE_INSTALLER_ASSET
        if destination.is_file():
            try:
                destination.unlink()
            except OSError:
                pass
        self._download_worker = _UpdateDownloadWorker(release, destination)
        self._download_worker.progress.connect(self.download_progress.emit)
        self._download_worker.completed.connect(self._on_download_completed)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.finished.connect(self._clear_download_worker)
        self._download_worker.start()

    @staticmethod
    def launch_installer(setup_path: str | Path) -> None:
        """Avvia l'installer Inno Setup e chiude l'app corrente."""
        path = Path(setup_path)
        if not path.is_file():
            raise FileNotFoundError(f"Installer non trovato: {path}")
        subprocess.Popen(
            [
                str(path),
                "/SILENT",
                "/CLOSEAPPLICATIONS",
                "/NORESTART",
            ],
            cwd=str(path.parent),
            close_fds=True,
        )
        logger.info("Installer aggiornamento avviato: %s", path)

    def _on_check_completed(self, release: object) -> None:
        self._busy = False
        if release is None:
            self._pending_release = None
            self.up_to_date.emit()
            return
        if not isinstance(release, ReleaseInfo):
            return
        if self._is_skipped(release.version):
            self._pending_release = None
            self.up_to_date.emit()
            return
        self._pending_release = release
        self.update_available.emit(release)
        if self._auto_apply_after_check:
            self._auto_apply_after_check = False
            self.download_update(release)

    def _on_check_failed(self, message: str) -> None:
        self._auto_apply_after_check = False
        self._busy = False
        self.check_failed.emit(message)

    def _on_download_completed(self, path: str) -> None:
        self._busy = False
        self._pending_release = None
        self.download_completed.emit(path)

    def _on_download_failed(self, message: str) -> None:
        self._busy = False
        self.download_failed.emit(message)

    def _clear_check_worker(self) -> None:
        self._check_worker = None

    def _clear_download_worker(self) -> None:
        self._download_worker = None

    def _is_skipped(self, version: str) -> bool:
        skipped = self._settings.value(config.UPDATE_SETTINGS_SKIP_VERSION_KEY, "")
        if not skipped:
            return False
        return not is_newer_version(version, str(skipped))

    def _touch_last_check(self) -> None:
        self._settings.setValue(
            config.UPDATE_SETTINGS_LAST_CHECK_KEY,
            int(time.time()),
        )

    def _is_on_cooldown(self) -> bool:
        raw = self._settings.value(config.UPDATE_SETTINGS_LAST_CHECK_KEY, 0)
        try:
            last = int(raw)
        except (TypeError, ValueError):
            last = 0
        if last <= 0:
            return False
        elapsed_hours = (time.time() - last) / 3600
        return elapsed_hours < config.UPDATE_CHECK_COOLDOWN_HOURS

    def _is_skipped_version_pending(self) -> bool:
        skipped = self._settings.value(config.UPDATE_SETTINGS_SKIP_VERSION_KEY, "")
        if not skipped:
            return False
        return not is_newer_version(config.APP_VERSION, str(skipped))
