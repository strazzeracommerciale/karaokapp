"""Motore mpv con la stessa interfaccia di VlcEngine, usato su Windows.

Il processo non viene chiuso quando si spegne il monitor esterno: resta in pausa
nel widget nascosto e, alla riaccensione, fa un solo salto alla posizione del
brano. Il tono (Rubber Band, da -5 a +5) vive sul lettore che ha l'audio.
"""

from __future__ import annotations

import ctypes
import json
import logging
import subprocess
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget

import config

logger = logging.getLogger(__name__)

DRIFT_LIMIT = 0.15
_PITCH_AF = "@rb:rubberband=pitch-scale={scale:.12f}:formant=preserved:engine=faster"


def mpv_executable() -> Path:
    """Eseguibile mpv accanto al programma, cartella ``mpv``."""
    bundled = config.INSTALL_DIR / "mpv" / "mpv.exe"
    if bundled.is_file():
        return bundled
    raise RuntimeError(f"mpv non trovato: {bundled}")


def semitone_ratio(steps: int) -> float:
    """Rapporto di frequenza per uno spostamento di `steps` semitoni."""
    return 2.0 ** (steps / 12.0)


def _lower_priority(pid: int) -> None:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x0200, False, pid)
    if not handle:
        return
    kernel.SetPriorityClass(handle, 0x00004000)
    kernel.CloseHandle(handle)


class _Pipe:
    def __init__(self, name: str) -> None:
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateFileW.restype = ctypes.c_void_p
        self.handle = None
        last_error = 0
        for _ in range(80):
            handle = self.kernel.CreateFileW(name, 0xC0000000, 0, None, 3, 0x80, None)
            invalid = ctypes.c_void_p(-1).value
            if handle and handle != invalid:
                self.handle = handle
                break
            last_error = ctypes.get_last_error()
            time.sleep(0.05)
        if not self.handle:
            raise RuntimeError(f"canale mpv non aperto, errore {last_error}")
        self.request_id = 0
        self.buffer = b""

    def call(self, *args: object, timeout: float = 0.8) -> dict:
        self.request_id += 1
        payload = (
            json.dumps({"command": list(args), "request_id": self.request_id}).encode("utf-8")
            + b"\n"
        )
        written = wintypes.DWORD()
        outgoing = ctypes.create_string_buffer(payload)
        ok = self.kernel.WriteFile(
            self.handle, outgoing, len(payload), ctypes.byref(written), None
        )
        if not ok:
            raise RuntimeError(f"scrittura verso mpv fallita, errore {ctypes.get_last_error()}")
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            for message in self._drain():
                if message.get("request_id") == self.request_id:
                    return message
            time.sleep(0.01)
        raise TimeoutError(args)

    def _drain(self) -> list[dict]:
        available = wintypes.DWORD()
        self.kernel.PeekNamedPipe(self.handle, None, 0, None, ctypes.byref(available), None)
        if available.value:
            chunk = ctypes.create_string_buffer(available.value)
            read = wintypes.DWORD()
            self.kernel.ReadFile(self.handle, chunk, available.value, ctypes.byref(read), None)
            self.buffer += chunk.raw[: read.value]
        messages: list[dict] = []
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line.decode("utf-8")))
            except json.JSONDecodeError:
                continue
        return messages

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class MpvEngine:
    """Lettore mpv embeddato in un widget Qt, oppure solo audio."""

    _alive: list["MpvEngine"] = []
    _role_seq = 0

    def __init__(self, *extra_args: str) -> None:
        flags = set(extra_args)
        self._no_video = "--no-video" in flags
        self._no_audio = "--no-audio" in flags
        self._pitch = "--karokapp-pitch" in flags
        self._hwdec_no = "--hwdec=no" in flags
        if self._no_video:
            role = "filler"
        elif self._no_audio:
            role = "ext"
        elif self._pitch:
            role = "karaoke"
        else:
            role = "video"
        MpvEngine._role_seq += 1
        self._role = f"{role}-{MpvEngine._role_seq}"
        self._pipe_name = rf"\\.\pipe\mpv-app-{ctypes.windll.kernel32.GetCurrentProcessId()}-{self._role}"
        self._proc: subprocess.Popen[bytes] | None = None
        self._pipe: _Pipe | None = None
        self._hwnd: int | None = None
        self._widget: QWidget | None = None
        self._path: str | None = None
        self._has_media = False
        self._paused = True
        self._held = False
        self._eof = False
        self._eof_sent = False
        self._stopped_at = 0.0
        self._semitones = 0
        self._volume = 100
        self._muted = False
        self._leader: MpvEngine | None = None
        self._position_callback: Callable[[float], None] | None = None
        self._end_callback: Callable[[], None] | None = None
        self._hold_until = 0.0
        self._ready_at = 0.0
        self._drift_hits = 0
        self._resyncs = 0
        self._position_timer = QTimer()
        self._position_timer.setInterval(500)
        self._position_timer.timeout.connect(self._emit_position)
        self._drift_timer = QTimer()
        self._drift_timer.setInterval(500)
        self._drift_timer.timeout.connect(self._correct_drift)
        MpvEngine._alive.append(self)

    def clone(self) -> "MpvEngine":
        """Secondo video senza audio, collegato all'orologio di questo lettore."""
        secondary = MpvEngine("--no-audio", "--hwdec=no")
        secondary._leader = self
        secondary._drift_timer.start()
        return secondary

    def set_output_widget(self, widget: QWidget) -> None:
        """Incorpora il video nel widget. Se la finestra è la stessa, non ricrea mpv."""
        self._widget = widget
        widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        hwnd = int(widget.winId())
        self._ensure_process(hwnd)

    def set_position_callback(self, callback: Callable[[float], None] | None) -> None:
        self._position_callback = callback
        if callback is not None:
            self._position_timer.start()

    def set_end_callback(self, callback: Callable[[], None] | None) -> None:
        self._end_callback = callback
        if callback is not None:
            self._position_timer.start()

    def set_semitones(self, steps: int) -> None:
        """Sposta il tono di `steps` semitoni rispetto all'originale, fra -5 e +5."""
        self._semitones = max(-5, min(5, int(steps)))
        if self._pitch and self._pipe is not None:
            self._command("set_property", "af", self._filter(), timeout=0.6)

    def semitones(self) -> int:
        return self._semitones

    def load(
        self,
        path_or_url: str,
        loop: bool = False,
        start_time: float = 0.0,
        audio_url: str | None = None,
    ) -> None:
        """Carica un file o uno stream. Il secondo schermo non ricarica lo stesso file."""
        if not path_or_url:
            return
        self._ensure_process(self._hwnd)
        self._command("set_property", "loop-file", "inf" if loop else "no")
        fresh_stop = self._stopped_at > 0 and (time.monotonic() - self._stopped_at) < 0.5
        same_file = (
            self._no_audio
            and self._has_media
            and self._path == path_or_url
            and not fresh_stop
            and not audio_url
        )
        self._eof = False
        self._eof_sent = False
        self._held = False
        self._ready_at = time.monotonic() + 1.5
        self._hold_until = time.monotonic() + 2.5
        self._drift_hits = 0
        if same_file:
            logger.info("Secondo schermo già sul brano, niente ricarica: %s", self._role)
            return
        options = f"start={start_time:.3f}" if start_time > 0.2 else ""
        if options:
            reply = self._command("loadfile", path_or_url, "replace", options, timeout=2.0)
        else:
            reply = self._command("loadfile", path_or_url, "replace", timeout=2.0)
        if reply is None or reply.get("error") not in (None, "success"):
            logger.error("Caricamento mpv non riuscito (%s): %s", self._role, reply)
            return
        self._path = path_or_url
        self._has_media = True
        self._paused = False
        self._command("set_property", "audio-files", [audio_url] if audio_url else [], timeout=1.5)
        if self._pitch:
            self._command("set_property", "af", self._filter(), timeout=1.5)
        self._command("set_property", "mute", self._muted, timeout=1.5)
        self._command("set_property", "volume", self._volume, timeout=1.5)
        logger.info("mpv carica %s (start=%.3f, ruolo=%s)", path_or_url, start_time, self._role)

    def play(self) -> None:
        self._ensure_process(self._hwnd)
        self._paused = False
        self._held = False
        self._command("set_property", "pause", False)
        if self._position_callback is not None or self._end_callback is not None:
            self._position_timer.start()

    def pause(self) -> None:
        self._paused = True
        self._command("set_property", "pause", True)

    def stop(self) -> None:
        """Ferma il brano. Il secondo schermo resta vivo, solo in pausa."""
        self._stopped_at = time.monotonic()
        self._paused = True
        self._eof = False
        self._eof_sent = False
        self._position_timer.stop()
        if self._proc is None:
            return
        if self._no_audio:
            self._held = True
            self._drift_hits = 0
            self._command("set_property", "pause", True)
            return
        self._held = False
        self._has_media = False
        self._command("stop")

    def seek(self, seconds: float) -> None:
        mode = "absolute+exact" if self._no_audio else "absolute"
        self._eof = False
        self._eof_sent = False
        self._command("seek", max(0.0, float(seconds)), mode, timeout=0.8)
        if self._no_audio:
            self._drift_hits = 0
            self._hold_until = time.monotonic() + 2.5
            self._ready_at = time.monotonic() + 1.2

    def set_mute(self, mute: bool) -> None:
        self._muted = bool(mute)
        if not self._no_audio:
            self._command("set_property", "mute", self._muted)

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        if not self._no_audio:
            self._command("set_property", "volume", self._volume)

    def get_position(self) -> float:
        duration = self.get_duration()
        if duration <= 0:
            return 0.0
        return max(0.0, min(1.0, (self.get_time() / 1000.0) / duration))

    def get_time(self) -> int:
        value = self._get("time-pos")
        if isinstance(value, (int, float)) and value >= 0:
            return int(float(value) * 1000)
        return 0

    def get_duration(self) -> float:
        value = self._get("duration")
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
        return 0.0

    def is_playing(self) -> bool:
        return self._has_media and not self._paused and not self._held and not self._eof

    def shutdown(self) -> None:
        proc = self._proc
        pipe = self._pipe
        self._proc = None
        self._pipe = None
        self._position_timer.stop()
        self._drift_timer.stop()
        if pipe is not None:
            try:
                pipe.call("quit", timeout=0.3)
            except Exception:
                pass
            pipe.close()
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    @classmethod
    def shutdown_all(cls) -> None:
        for engine in list(cls._alive):
            engine.shutdown()
        cls._alive.clear()

    def _filter(self) -> str:
        return _PITCH_AF.format(scale=semitone_ratio(self._semitones))

    def _ensure_process(self, hwnd: int | None) -> None:
        if self._proc is not None and self._proc.poll() is None:
            if hwnd and hwnd != self._hwnd:
                self._hwnd = hwnd
                self._command("set_property", "wid", hwnd, timeout=0.6)
            return
        if not self._no_video and not hwnd:
            return
        mpv_bin = mpv_executable()
        log_dir = config.LOG_PATH.parent
        log_dir.mkdir(exist_ok=True)
        args = [
            str(mpv_bin),
            "--no-config",
            "--idle=yes",
            "--keep-open=yes",
            "--force-window=no",
            "--input-default-bindings=no",
            "--input-vo-keyboard=no",
            "--osc=no",
            "--osd-level=0",
            "--ytdl=no",
            "--user-agent=Mozilla/5.0",
            "--referrer=https://www.youtube.com/",
            f"--input-ipc-server={self._pipe_name}",
            f"--log-file={log_dir / f'mpv-{self._role}.log'}",
            "--msg-level=all=warn",
            f"--volume={self._volume}",
        ]
        if self._no_video:
            args.append("--no-video")
        else:
            hwdec = "no" if self._hwdec_no or self._no_audio else "auto"
            args.extend(
                [
                    "--vo=gpu",
                    "--gpu-context=d3d11",
                    f"--hwdec={hwdec}",
                    f"--wid={hwnd}",
                ]
            )
        if self._no_audio:
            args.append("--no-audio")
        if self._pitch:
            args.append(f"--af={self._filter()}")
        self._proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            self._pipe = _Pipe(self._pipe_name)
        except Exception:
            self._proc.kill()
            self._proc = None
            raise
        self._hwnd = hwnd
        if self._no_audio and self._proc.pid:
            _lower_priority(self._proc.pid)
        logger.info("mpv avviato, ruolo %s", self._role)

    def _command(self, *args: object, timeout: float = 0.5) -> dict | None:
        if self._pipe is None:
            return None
        try:
            reply = self._pipe.call(*args, timeout=timeout)
        except Exception as exc:
            logger.warning("comando mpv %s fallito (%s): %s", args[:2], self._role, exc)
            return None
        return reply

    def _get(self, name: str) -> object:
        reply = self._command("get_property", name, timeout=0.25)
        if not reply or reply.get("error") not in (None, "success"):
            return None
        return reply.get("data")

    def _emit_position(self) -> None:
        if self._pipe is None or self._held:
            return
        position = self._get("time-pos")
        duration = self._get("duration")
        eof = self._get("eof-reached") is True
        if eof and not self._eof:
            self._eof = True
            self._paused = True
        if (
            self._position_callback is not None
            and isinstance(position, (int, float))
            and isinstance(duration, (int, float))
            and duration > 0
        ):
            ratio = max(0.0, min(1.0, float(position) / float(duration)))
            self._position_callback(ratio)
        if eof and not self._eof_sent and self._end_callback is not None:
            self._eof_sent = True
            self._end_callback()

    def _correct_drift(self) -> None:
        leader = self._leader
        if leader is None or self._held or self._paused or not self._has_media:
            return
        if leader._paused or leader._held or not leader._has_media:
            return
        now = time.monotonic()
        if now < self._hold_until or now < self._ready_at:
            return
        here = self._get("time-pos")
        there = leader._get("time-pos")
        if not isinstance(here, (int, float)) or not isinstance(there, (int, float)):
            return
        gap = float(there) - float(here)
        if abs(gap) <= DRIFT_LIMIT:
            self._drift_hits = 0
            return
        self._drift_hits += 1
        if self._drift_hits < 3:
            return
        self._command("seek", float(there), "absolute+exact", timeout=0.8)
        self._resyncs += 1
        self._drift_hits = 0
        self._hold_until = time.monotonic() + 2.5
        logger.info(
            "Secondo schermo riallineato di %.0f ms (totale %d)",
            gap * 1000,
            self._resyncs,
        )
