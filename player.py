"""Playback engine: a thin wrapper over libVLC.

libVLC plays almost any container/codec, and its video output can be drawn
inside a Tk widget, which is what makes a single-window player possible.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from commands import SPEED_LADDER

MIN_RATE = 0.25
MAX_RATE = 4.0


class PlayerError(RuntimeError):
    """Raised when VLC is missing or cannot start."""


class Player:
    def __init__(self, widget) -> None:
        try:
            import vlc  # type: ignore
        except ImportError as exc:
            raise PlayerError(
                "python-vlc is not installed.\n\n"
                "Run:  pip install python-vlc\n"
                "and install the VLC desktop app from https://www.videolan.org/vlc/"
            ) from exc

        self._vlc = vlc
        try:
            self._instance = vlc.Instance("--no-video-title-show", "--quiet")
        except Exception as exc:  # libvlc present but unusable
            raise PlayerError(
                "VLC could not start. Install the VLC desktop app (64-bit) from "
                "https://www.videolan.org/vlc/ and try again.\n\n"
                f"Details: {exc}"
            ) from exc
        if self._instance is None:
            raise PlayerError(
                "VLC could not start. Install the VLC desktop app (64-bit) from "
                "https://www.videolan.org/vlc/ and try again."
            )

        self._player = self._instance.media_player_new()
        self._widget = widget
        self._path: Optional[str] = None
        self._volume = 100
        self._attach_output()

    # -- window embedding ---------------------------------------------------

    def _attach_output(self) -> None:
        """Tell VLC which native window to draw into."""
        try:
            self._widget.update_idletasks()
            handle = self._widget.winfo_id()
        except Exception:
            return
        try:
            if sys.platform.startswith("linux"):
                self._player.set_xwindow(handle)
            elif sys.platform == "darwin":
                self._player.set_nsobject(handle)
            else:
                self._player.set_hwnd(handle)
        except Exception:
            pass  # VLC falls back to its own window; playback still works

    # -- media --------------------------------------------------------------

    def open(self, path: str) -> None:
        if not os.path.isfile(path):
            raise PlayerError(f"No such file: {path}")
        media = self._instance.media_new(path)
        self._player.set_media(media)
        self._path = path
        self._attach_output()
        self._player.play()

    @property
    def path(self) -> Optional[str]:
        return self._path

    # -- transport ----------------------------------------------------------

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle_play(self) -> None:
        if self._player.is_playing():
            self._player.pause()
        else:
            self._player.play()

    def stop(self) -> None:
        self._player.stop()

    def restart(self) -> None:
        self._player.set_time(0)
        self._player.play()

    @property
    def is_playing(self) -> bool:
        return bool(self._player.is_playing())

    @property
    def time_ms(self) -> int:
        return max(0, int(self._player.get_time()))

    @property
    def length_ms(self) -> int:
        return int(self._player.get_length())

    def seek_by(self, seconds: float) -> None:
        """Move relative to the current position, clamped to the video."""
        if self._player.get_media() is None:
            return
        target = self.time_ms + int(seconds * 1000)
        target = max(0, target)
        length = self.length_ms
        if length > 0:
            target = min(target, length - 1000)
        self._player.set_time(target)

    def seek_to(self, seconds: float) -> None:
        if self._player.get_media() is None:
            return
        target = max(0, int(seconds * 1000))
        length = self.length_ms
        if length > 0:
            target = min(target, length - 1000)
        self._player.set_time(target)

    # -- audio --------------------------------------------------------------

    def get_volume(self) -> int:
        volume = self._player.audio_get_volume()
        return self._volume if volume < 0 else int(volume)

    def set_volume(self, volume: float) -> None:
        value = max(0, min(100, int(round(volume))))
        self._volume = value
        self._player.audio_set_volume(value)

    def change_volume(self, delta: float) -> None:
        self.set_volume(self.get_volume() + delta)

    def set_mute(self, muted: bool) -> None:
        self._player.audio_set_mute(bool(muted))

    def get_mute(self) -> bool:
        return bool(self._player.audio_get_mute())

    def toggle_mute(self) -> None:
        self.set_mute(not self.get_mute())

    # -- speed --------------------------------------------------------------

    def set_rate(self, rate: float) -> None:
        self._player.set_rate(max(MIN_RATE, min(MAX_RATE, float(rate))))

    def get_rate(self) -> float:
        rate = self._player.get_rate()
        return 1.0 if rate <= 0 else float(rate)

    def step_rate(self, direction: float) -> None:
        """Walk up or down the 0.5 / 1 / 1.5 / 2 ladder."""
        current = self.get_rate()
        ladder = sorted(SPEED_LADDER)
        if direction > 0:
            nxt = next((s for s in ladder if s > current + 0.01), ladder[-1])
        else:
            nxt = next((s for s in reversed(ladder) if s < current - 0.01), ladder[0])
        self.set_rate(nxt)

    # -- housekeeping -------------------------------------------------------

    def release(self) -> None:
        try:
            self._player.stop()
            self._player.release()
            self._instance.release()
        except Exception:
            pass
