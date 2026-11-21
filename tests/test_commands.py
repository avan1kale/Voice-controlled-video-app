"""Unit tests for the command parser.  Run:  python -m unittest discover tests"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import Command, describe, format_time, parse_command, parse_time  # noqa: E402


class TransportTests(unittest.TestCase):
    def test_play(self):
        for phrase in ("play", "Play.", "resume", "unpause", "continue playing"):
            self.assertEqual(parse_command(phrase), Command("play"), phrase)

    def test_pause(self):
        for phrase in ("pause", "pause the video", "Pause!", "hold on"):
            self.assertEqual(parse_command(phrase), Command("pause"), phrase)

    def test_stop(self):
        self.assertEqual(parse_command("stop"), Command("stop"))
        self.assertEqual(parse_command("stop the video"), Command("stop"))

    def test_restart(self):
        for phrase in ("restart", "replay", "start over", "from the beginning",
                       "go back to the start"):
            self.assertEqual(parse_command(phrase), Command("restart"), phrase)

    def test_open(self):
        for phrase in ("open", "open a video", "open file", "load movie", "browse"):
            self.assertEqual(parse_command(phrase), Command("open"), phrase)


class SeekTests(unittest.TestCase):
    def test_forward_default(self):
        self.assertEqual(parse_command("forward"), Command("seek_rel", 10.0))
        self.assertEqual(parse_command("fast forward"), Command("seek_rel", 10.0))

    def test_forward_with_amount(self):
        self.assertEqual(parse_command("forward 30 seconds"), Command("seek_rel", 30.0))
        self.assertEqual(parse_command("forward ten seconds"), Command("seek_rel", 10.0))
        self.assertEqual(parse_command("skip ahead twenty five seconds"),
                         Command("seek_rel", 25.0))
        self.assertEqual(parse_command("advance 1 minute"), Command("seek_rel", 60.0))

    def test_rewind_default(self):
        self.assertEqual(parse_command("rewind"), Command("seek_rel", -10.0))
        self.assertEqual(parse_command("go back"), Command("seek_rel", -10.0))

    def test_rewind_with_amount(self):
        self.assertEqual(parse_command("rewind 5 seconds"), Command("seek_rel", -5.0))
        self.assertEqual(parse_command("go back ten seconds"), Command("seek_rel", -10.0))
        self.assertEqual(parse_command("back 5"), Command("seek_rel", -5.0))

    def test_fast_forward_is_not_a_speed_change(self):
        self.assertEqual(parse_command("fast forward 20 seconds"), Command("seek_rel", 20.0))

    def test_jump_to_timestamp(self):
        self.assertEqual(parse_command("jump to 1:30"), Command("seek_to", 90.0))
        self.assertEqual(parse_command("go to 2:05"), Command("seek_to", 125.0))
        self.assertEqual(parse_command("jump to 1 hour 2 minutes"), Command("seek_to", 3720.0))
        self.assertEqual(parse_command("skip to 45 seconds"), Command("seek_to", 45.0))
        self.assertEqual(parse_command("take me to the 1 minute 30 mark"),
                         Command("seek_to", 90.0))

    def test_jump_does_not_swallow_relative_seek(self):
        self.assertEqual(parse_command("go back 10 seconds"), Command("seek_rel", -10.0))
        self.assertNotEqual(
            (parse_command("go back 10 seconds") or Command("")).action, "seek_to"
        )


class VolumeTests(unittest.TestCase):
    def test_volume_up(self):
        for phrase in ("volume up", "louder", "turn it up", "increase volume"):
            self.assertEqual(parse_command(phrase), Command("volume_rel", 10.0), phrase)

    def test_volume_down(self):
        for phrase in ("volume down", "quieter", "turn it down", "lower the volume"):
            self.assertEqual(parse_command(phrase), Command("volume_rel", -10.0), phrase)

    def test_volume_with_amount(self):
        self.assertEqual(parse_command("volume up 20"), Command("volume_rel", 20.0))
        self.assertEqual(parse_command("increase volume by thirty"),
                         Command("volume_rel", 30.0))

    def test_volume_set(self):
        self.assertEqual(parse_command("set volume to 50"), Command("volume_set", 50.0))
        self.assertEqual(parse_command("volume 70"), Command("volume_set", 70.0))

    def test_mute_unmute(self):
        self.assertEqual(parse_command("mute"), Command("mute"))
        self.assertEqual(parse_command("mute the sound"), Command("mute"))
        self.assertEqual(parse_command("unmute"), Command("unmute"))
        self.assertEqual(parse_command("sound on"), Command("unmute"))
        self.assertNotEqual(parse_command("unmute"), Command("mute"))


class SpeedTests(unittest.TestCase):
    def test_explicit_speed(self):
        self.assertEqual(parse_command("speed 1.5"), Command("speed", 1.5))
        self.assertEqual(parse_command("set speed to 2"), Command("speed", 2.0))
        self.assertEqual(parse_command("play at 0.5x"), Command("speed", 0.5))
        self.assertEqual(parse_command("1.5x"), Command("speed", 1.5))
        self.assertEqual(parse_command("two times speed"), Command("speed", 2.0))

    def test_named_speeds(self):
        self.assertEqual(parse_command("normal speed"), Command("speed", 1.0))
        self.assertEqual(parse_command("half speed"), Command("speed", 0.5))
        self.assertEqual(parse_command("double speed"), Command("speed", 2.0))

    def test_ladder_steps(self):
        self.assertEqual(parse_command("faster"), Command("speed_step", 1.0))
        self.assertEqual(parse_command("speed up"), Command("speed_step", 1.0))
        self.assertEqual(parse_command("slower"), Command("speed_step", -1.0))
        self.assertEqual(parse_command("slow down"), Command("speed_step", -1.0))


class DisplayTests(unittest.TestCase):
    def test_fullscreen(self):
        self.assertEqual(parse_command("fullscreen"), Command("fullscreen"))
        self.assertEqual(parse_command("go full screen"), Command("fullscreen"))

    def test_exit_fullscreen(self):
        self.assertEqual(parse_command("exit fullscreen"), Command("windowed"))
        self.assertEqual(parse_command("leave full screen"), Command("windowed"))

    def test_quit(self):
        self.assertEqual(parse_command("quit"), Command("quit"))


class TimeTests(unittest.TestCase):
    def test_parse_time(self):
        self.assertEqual(parse_time("1:30"), 90.0)
        self.assertEqual(parse_time("1:02:03"), 3723.0)
        self.assertEqual(parse_time("90"), 90.0)
        self.assertEqual(parse_time("1 minute 30 seconds"), 90.0)
        self.assertEqual(parse_time("one minute and thirty seconds"), 90.0)
        self.assertEqual(parse_time("2 min"), 120.0)
        self.assertEqual(parse_time("1.5 minutes"), 90.0)
        self.assertIsNone(parse_time("the end"))

    def test_format_time(self):
        self.assertEqual(format_time(0), "0:00")
        self.assertEqual(format_time(90), "1:30")
        self.assertEqual(format_time(3723), "1:02:03")


class NoiseTests(unittest.TestCase):
    def test_empty_and_nonsense(self):
        for phrase in ("", "   ", "what is the weather today", "mmm"):
            self.assertIsNone(parse_command(phrase), phrase)

    def test_fuzzy_mishears(self):
        self.assertEqual(parse_command("paws"), Command("pause"))
        self.assertEqual(parse_command("pley"), Command("play"))

    def test_describe(self):
        self.assertEqual(describe(Command("seek_rel", 10.0)), "Forward 10 s")
        self.assertEqual(describe(Command("seek_rel", -5.0)), "Rewind 5 s")
        self.assertEqual(describe(Command("seek_to", 90.0)), "Jump to 1:30")
        self.assertEqual(describe(Command("speed", 1.5)), "Speed 1.5x")


if __name__ == "__main__":
    unittest.main(verbosity=2)
