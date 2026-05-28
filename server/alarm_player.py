"""Reproduz alarme sonoro quando ha violacao de EPI ativa."""

from __future__ import annotations

import logging
import platform
import subprocess
import threading
import time

log = logging.getLogger("tortuga")


class AlarmPlayer:
    """Toca um arquivo WAV em loop enquanto ha violacao nao-silenciada."""

    def __init__(self, status, sound_file: str = "static/alarm.wav"):
        self._status = status
        self._sound_file = sound_file
        self._stop_flag = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_flag.set()

    def _loop(self) -> None:
        while not self._stop_flag.is_set():
            self._tick()
            time.sleep(0.2)

    def _tick(self) -> None:
        """Uma iteracao: toca som se deveria, ou aguarda."""
        data = self._status.get()
        if data["blocked"] and not data["silenced"]:
            self._play_once()

    def _play_once(self) -> None:
        cmd = self._build_command()
        if cmd is None:
            return
        try:
            subprocess.run(cmd, check=False, capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            log.warning("Falha ao tocar alarme: %s", exc)

    def _build_command(self) -> list[str] | None:
        system = platform.system()
        if system == "Darwin":
            return ["afplay", self._sound_file]
        if system == "Linux":
            return ["aplay", "-q", self._sound_file]
        if system == "Windows":
            # Windows usa biblioteca padrao winsound, nao subprocess
            return None
        return None
