"""Entry point: python main.py [video-file]

    python main.py                      # empty player, open a file from the app
    python main.py C:\\clips\\movie.mp4   # open this file on start
    python main.py --version
"""

from __future__ import annotations

import argparse
import sys

from version import APP_VERSION


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="voice-player", description="Voice-controlled local video player"
    )
    parser.add_argument(
        "--version", action="version", version=f"Voice Player {APP_VERSION}"
    )
    parser.add_argument("video", nargs="?", help="video file to open on start")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    print(f"Voice Player {APP_VERSION}")  # build stamp, readable without a window

    try:
        import tkinter as tk
    except Exception:
        print(
            "tkinter is missing. On Linux install it with:\n"
            "  sudo apt install python3-tk\n"
            "On Windows/macOS reinstall Python from python.org with tcl/tk ticked."
        )
        return 1

    from app import VideoPlayerApp
    from player import PlayerError

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Could not open a window: {exc}")
        return 1

    try:
        VideoPlayerApp(root, initial_video=args.video)
    except PlayerError as exc:
        from tkinter import messagebox

        print(exc)
        messagebox.showerror("Cannot start the player", str(exc))
        root.destroy()
        return 1

    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
