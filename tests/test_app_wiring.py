"""Headless wiring test for the GUI.

Tkinter needs a display, so this test swaps in a stand-in `tkinter` module and
a fake player, then drives the real `VideoPlayerApp` logic: voice text in,
player calls out. Run it anywhere:

    python -m unittest discover tests
"""

from __future__ import annotations

import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# --------------------------------------------------------------- tk stub ----

class _Widget:
    def __init__(self, *args, **kwargs):
        self.options = dict(kwargs)

    def __getattr__(self, name):
        return lambda *a, **k: None

    def __getitem__(self, key):
        return _Widget()

    def __setitem__(self, key, value):
        pass


def _install_tk_stub() -> None:
    if "tkinter" in sys.modules:
        return
    tk = types.ModuleType("tkinter")

    class TclError(Exception):
        pass

    for name in ("Tk", "Toplevel", "Frame", "Label", "Button", "Entry", "Text",
                 "Scale", "OptionMenu", "StringVar", "BooleanVar", "Menu"):
        setattr(tk, name, type(name, (_Widget,), {}))
    tk.TclError = TclError

    filedialog = types.ModuleType("tkinter.filedialog")
    filedialog.askopenfilename = lambda **kwargs: ""
    messagebox = types.ModuleType("tkinter.messagebox")
    messagebox.showerror = lambda *a, **k: None

    tk.filedialog = filedialog
    tk.messagebox = messagebox
    sys.modules["tkinter"] = tk
    sys.modules["tkinter.filedialog"] = filedialog
    sys.modules["tkinter.messagebox"] = messagebox


_install_tk_stub()

import tkinter  # noqa: E402  (the stub)
import app  # noqa: E402
from commands import SPEED_LADDER  # noqa: E402


# ------------------------------------------------------------ fake player ----

class FakePlayer:
    def __init__(self, widget):
        self.path = None
        self.time = 0
        self.length = 600_000
        self.volume = 100
        self.muted = False
        self.rate = 1.0
        self.playing = False
        self.released = False

    def open(self, path):
        self.path = path
        self.playing = True

    def play(self):
        self.playing = True

    def pause(self):
        self.playing = False

    def toggle_play(self):
        self.playing = not self.playing

    def stop(self):
        self.playing = False
        self.time = 0

    def restart(self):
        self.time = 0
        self.playing = True

    @property
    def is_playing(self):
        return self.playing

    @property
    def time_ms(self):
        return self.time

    @property
    def length_ms(self):
        return self.length

    def seek_by(self, seconds):
        self.time = max(0, min(self.length, self.time + int(seconds * 1000)))

    def seek_to(self, seconds):
        self.time = max(0, min(self.length, int(seconds * 1000)))

    def get_volume(self):
        return self.volume

    def set_volume(self, volume):
        self.volume = max(0, min(100, int(round(volume))))

    def change_volume(self, delta):
        self.set_volume(self.volume + delta)

    def set_mute(self, muted):
        self.muted = bool(muted)

    def get_mute(self):
        return self.muted

    def toggle_mute(self):
        self.muted = not self.muted

    def set_rate(self, rate):
        self.rate = float(rate)

    def get_rate(self):
        return self.rate

    def step_rate(self, direction):
        ladder = sorted(SPEED_LADDER)
        if direction > 0:
            self.rate = next((s for s in ladder if s > self.rate + 0.01), ladder[-1])
        else:
            self.rate = next((s for s in reversed(ladder) if s < self.rate - 0.01), ladder[0])

    def release(self):
        self.released = True


class AppTests(unittest.TestCase):
    def setUp(self):
        app.Player = FakePlayer
        app.messagebox = tkinter.messagebox
        self.root = tkinter.Tk()
        self.app = app.VideoPlayerApp(self.root)
        self.player = self.app.player

    def say(self, text):
        self.app._handle_heard(text)

    def test_transport(self):
        self.say("play")
        self.assertTrue(self.player.playing)
        self.say("pause")
        self.assertFalse(self.player.playing)
        self.say("stop")
        self.assertFalse(self.player.playing)
        self.say("restart")
        self.assertTrue(self.player.playing)

    def test_seek(self):
        self.player.time = 30_000
        self.say("forward ten seconds")
        self.assertEqual(self.player.time, 40_000)
        self.say("rewind 5 seconds")
        self.assertEqual(self.player.time, 35_000)
        self.say("jump to 2:00")
        self.assertEqual(self.player.time, 120_000)

    def test_volume_and_mute(self):
        self.say("volume up")
        self.assertEqual(self.player.volume, 100)
        self.say("volume down")
        self.assertEqual(self.player.volume, 90)
        self.say("set volume to 40")
        self.assertEqual(self.player.volume, 40)
        self.say("mute")
        self.assertTrue(self.player.muted)
        self.say("unmute")
        self.assertFalse(self.player.muted)

    def test_speed(self):
        self.say("speed 1.5")
        self.assertEqual(self.player.rate, 1.5)
        self.say("faster")
        self.assertEqual(self.player.rate, 2.0)
        self.say("normal speed")
        self.assertEqual(self.player.rate, 1.0)

    def test_open_command(self):
        tkinter.filedialog.askopenfilename = lambda **kwargs: "/tmp/clip.mp4"
        self.say("open a video")
        self.assertEqual(self.player.path, "/tmp/clip.mp4")

    def test_fullscreen_toggle(self):
        seen = []
        self.root.attributes = lambda *a: seen.append(a)
        self.say("fullscreen")
        self.assertEqual(seen[-1], ("-fullscreen", True))
        self.say("exit fullscreen")
        self.assertEqual(seen[-1], ("-fullscreen", False))

    def test_unparsed_speech_is_ignored(self):
        self.say("what is the weather like")
        self.assertFalse(self.player.playing)

    def test_typed_command_path(self):
        self.app.entry.get = lambda: "stop"
        self.player.playing = True
        self.app._run_typed_command()
        self.assertFalse(self.player.playing)


if __name__ == "__main__":
    unittest.main(verbosity=2)
