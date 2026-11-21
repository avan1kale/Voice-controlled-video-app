"""Tkinter front end for the voice-controlled video player."""

from __future__ import annotations

import os
import queue
import re
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional

import config
from commands import SPEED_LADDER, Command, describe, format_time, parse_command
from player import Player, PlayerError
from version import APP_VERSION  # noqa: F401  (re-exported for convenience)
from voice import VoiceListener

BG = "#0f0f11"
PANEL = "#17171a"
BUTTON = "#232327"
BUTTON_ACTIVE = "#34343a"
TEXT = "#e8e8ea"
MUTED = "#9a9aa2"
ACCENT = "#4f8cff"

VIDEO_TYPES = (
    "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v *.mpg *.mpeg *.ts *.3gp"
)


class VideoPlayerApp:
    def __init__(self, root: tk.Tk, initial_video: Optional[str] = None) -> None:
        self.root = root
        self.root.title(f"Voice Player {APP_VERSION}")
        self.root.geometry("1040x700")
        self.root.minsize(760, 520)
        self.root.configure(bg=BG)

        self.events: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.listener: Optional[VoiceListener] = None
        self._seeking = False
        self._volume_dragging = False
        self._fullscreen = False

        self._build_ui()
        self.player = Player(self.video)
        self._bind_keys()

        self._sync_volume_scale()
        self._poll_events()
        self._tick()

        if initial_video:
            self.root.after(400, lambda: self._open_path(initial_video))

        self._log(f"Voice Player {APP_VERSION} ready. Open a video, then start listening.")

    # ------------------------------------------------------------------ UI --

    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.video = tk.Frame(self.root, bg="#000000", bd=0, highlightthickness=0)
        self.video.grid(row=0, column=0, sticky="nsew")

        self.controls = tk.Frame(self.root, bg=PANEL, padx=12, pady=10)
        self.controls.grid(row=1, column=0, sticky="ew")

        self._build_seek_row()
        self._build_buttons_row()
        self._build_voice_row()
        self._build_log()

    def _build_seek_row(self) -> None:
        row = tk.Frame(self.controls, bg=PANEL)
        row.pack(fill="x", pady=(0, 8))

        self.time_label = tk.Label(
            row, text="0:00", width=7, anchor="w", bg=PANEL, fg=TEXT
        )
        self.time_label.pack(side="left")

        self.seek = tk.Scale(
            row,
            from_=0,
            to=1000,
            orient="horizontal",
            showvalue=False,
            bg=PANEL,
            fg=TEXT,
            troughcolor="#2b2b30",
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            activebackground=ACCENT,
        )
        self.seek.pack(side="left", fill="x", expand=True, padx=8)
        self.seek.bind("<ButtonPress-1>", lambda _e: self._start_seek())
        self.seek.bind("<ButtonRelease-1>", self._end_seek)

        self.duration_label = tk.Label(
            row, text="0:00", width=7, anchor="e", bg=PANEL, fg=TEXT
        )
        self.duration_label.pack(side="left")

    def _build_buttons_row(self) -> None:
        row = tk.Frame(self.controls, bg=PANEL)
        row.pack(fill="x", pady=(0, 8))

        self._button(row, "Open", self.open_file, 7).pack(side="left", padx=(0, 6))
        self._button(row, "Restart", lambda: self.execute(Command("restart")), 8).pack(
            side="left", padx=3
        )
        self._button(row, "-10 s", lambda: self.execute(Command("seek_rel", -10.0)), 6).pack(
            side="left", padx=3
        )
        self.play_button = self._button(row, "Play", self.toggle_play, 8)
        self.play_button.pack(side="left", padx=3)
        self._button(row, "+10 s", lambda: self.execute(Command("seek_rel", 10.0)), 6).pack(
            side="left", padx=3
        )
        self._button(row, "Stop", lambda: self.execute(Command("stop")), 6).pack(
            side="left", padx=3
        )
        self.mute_button = self._button(row, "Mute", self.toggle_mute, 6)
        self.mute_button.pack(side="left", padx=3)

        tk.Label(row, text="Speed", bg=PANEL, fg=MUTED).pack(side="left", padx=(14, 4))
        self.speed_var = tk.StringVar(value="1.0x")
        speed_menu = tk.OptionMenu(
            row, self.speed_var, *[f"{s:g}x" for s in SPEED_LADDER], command=self._on_speed_menu
        )
        speed_menu.config(
            bg=BUTTON, fg=TEXT, activebackground=BUTTON_ACTIVE, activeforeground=TEXT,
            relief="flat", bd=0, highlightthickness=0, width=5,
        )
        speed_menu["menu"].config(bg=BUTTON, fg=TEXT)
        speed_menu.pack(side="left")

        tk.Label(row, text="Volume", bg=PANEL, fg=MUTED).pack(side="left", padx=(14, 4))
        self.volume = tk.Scale(
            row,
            from_=0,
            to=100,
            orient="horizontal",
            showvalue=False,
            length=120,
            bg=PANEL,
            fg=TEXT,
            troughcolor="#2b2b30",
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            activebackground=ACCENT,
            command=self._on_volume_scale,
        )
        self.volume.pack(side="left")
        self.volume.bind("<ButtonPress-1>", lambda _e: setattr(self, "_volume_dragging", True))
        self.volume.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_volume_dragging", False))

        self._button(row, "Fullscreen", lambda: self.set_fullscreen(True), 10).pack(
            side="right"
        )

    def _build_voice_row(self) -> None:
        row = tk.Frame(self.controls, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))

        self.listen_button = self._button(row, "Start listening", self.toggle_listening, 14)
        self.listen_button.pack(side="left")

        self.voice_status = tk.Label(
            row, text="Microphone idle", bg=PANEL, fg=MUTED, anchor="w"
        )
        self.voice_status.pack(side="left", padx=10)

        tk.Label(row, text="Type a command", bg=PANEL, fg=MUTED).pack(side="left", padx=(16, 4))
        self.entry = tk.Entry(
            row, bg="#101012", fg=TEXT, insertbackground=TEXT, relief="flat",
            highlightthickness=1, highlightbackground="#2b2b30", highlightcolor=ACCENT,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", self._run_typed_command)
        self._button(row, "Run", self._run_typed_command, 5).pack(side="left", padx=6)

    def _build_log(self) -> None:
        self.log = tk.Text(
            self.controls, height=5, bg="#101012", fg="#a8c7a8", relief="flat",
            highlightthickness=1, highlightbackground="#2b2b30", wrap="word",
        )
        self.log.pack(fill="x")
        self.log.configure(state="disabled")

    def _button(self, parent, text: str, command, width: int = 8) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            bg=BUTTON,
            fg=TEXT,
            activebackground=BUTTON_ACTIVE,
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=6,
            pady=5,
            cursor="hand2",
        )

    # ------------------------------------------------------------- actions --

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Open a video",
            filetypes=[("Video files", VIDEO_TYPES), ("All files", "*.*")],
        )
        if path:
            self._open_path(path)

    def _open_path(self, path: str) -> None:
        try:
            self.player.open(path)
        except PlayerError as exc:
            messagebox.showerror("Cannot open video", str(exc))
            return
        name = os.path.basename(path)
        self.root.title(f"{name} - Voice Player {APP_VERSION}")
        self._log(f"Opened {name}")
        self.speed_var.set(f"{self.player.get_rate():g}x")

    def toggle_play(self) -> None:
        if self.player.path is None:
            self.open_file()
            return
        self.player.toggle_play()

    def toggle_mute(self) -> None:
        self.player.toggle_mute()
        self.mute_button.config(text="Unmute" if self.player.get_mute() else "Mute")

    def _on_speed_menu(self, value: str) -> None:
        try:
            rate = float(value.rstrip("x"))
        except ValueError:
            return
        self.execute(Command("speed", rate))

    def set_fullscreen(self, on: bool) -> None:
        self._fullscreen = on
        self.root.attributes("-fullscreen", on)
        if on:
            self.controls.grid_remove()
        else:
            self.controls.grid()
            self.root.focus_set()

    def execute(self, command: Command) -> None:
        action, value = command.action, command.value
        try:
            if action == "open":
                self.open_file()
            elif action == "play":
                self.player.play()
            elif action == "pause":
                self.player.pause()
            elif action == "stop":
                self.player.stop()
            elif action == "restart":
                self.player.restart()
            elif action == "seek_rel" and value is not None:
                self.player.seek_by(value)
            elif action == "seek_to" and value is not None:
                self.player.seek_to(value)
            elif action == "volume_rel" and value is not None:
                self.player.change_volume(value)
                self._sync_volume_scale()
            elif action == "volume_set" and value is not None:
                self.player.set_volume(value)
                self._sync_volume_scale()
            elif action == "mute":
                self.player.set_mute(True)
                self.mute_button.config(text="Unmute")
            elif action == "unmute":
                self.player.set_mute(False)
                self.mute_button.config(text="Mute")
            elif action == "speed" and value is not None:
                self.player.set_rate(value)
                self.speed_var.set(f"{self.player.get_rate():g}x")
            elif action == "speed_step" and value is not None:
                self.player.step_rate(value)
                self.speed_var.set(f"{self.player.get_rate():g}x")
            elif action == "fullscreen":
                self.set_fullscreen(True)
            elif action == "windowed":
                self.set_fullscreen(False)
            elif action == "quit":
                self.on_close()
        except PlayerError as exc:
            self._log(f"Error: {exc}")

    # --------------------------------------------------------------- voice --

    def toggle_listening(self) -> None:
        if self.listener is not None and self.listener.is_alive():
            self.listener.stop()
            self.listener = None
            self.listen_button.config(text="Start listening")
            self.voice_status.config(text="Microphone idle")
            self._log("Voice control off")
            return

        self.listener = VoiceListener(
            self.events,
            language=config.LANGUAGE,
            backend=config.BACKEND,
            model_path=config.VOSK_MODEL_PATH,
            device_index=config.MIC_DEVICE_INDEX,
        )
        self.listener.start()
        self.listen_button.config(text="Stop listening")
        self._log("Voice control on - try \"pause\", \"forward 10 seconds\", \"volume up\"")

    def _handle_heard(self, text: str) -> None:
        self._log(f'Heard: "{text}"')
        phrase = text
        if config.WAKE_WORD:
            if config.WAKE_WORD.lower() not in text.lower():
                return
            phrase = re.sub(
                rf"\b{re.escape(config.WAKE_WORD)}\b", " ", text, flags=re.IGNORECASE
            )
        command = parse_command(phrase)
        if command is None:
            self._log("   no matching command")
            return
        self._log(f"   -> {describe(command)}")
        self.execute(command)

    def _run_typed_command(self, _event=None) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._handle_heard(text)

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "heard":
                    self._handle_heard(payload)
                elif kind == "status":
                    self.voice_status.config(text=payload)
                    if payload in ("Microphone off",):
                        self.listen_button.config(text="Start listening")
                        self.listener = None
                elif kind == "error":
                    self.voice_status.config(text=payload)
                    self._log(f"Voice: {payload}")
        except queue.Empty:
            pass
        self.root.after(120, self._poll_events)

    # ------------------------------------------------------------ playback --

    def _start_seek(self) -> None:
        self._seeking = True

    def _end_seek(self, _event=None) -> None:
        self._seeking = False
        length = self.player.length_ms
        if length > 0:
            self.player.seek_to(length * self.seek.get() / 1000.0)

    def _on_volume_scale(self, value: str) -> None:
        if self._volume_dragging:
            try:
                self.player.set_volume(float(value))
            except ValueError:
                pass

    def _sync_volume_scale(self) -> None:
        if self._volume_dragging:
            return
        self.volume.set(self.player.get_volume())

    def _tick(self) -> None:
        try:
            position = self.player.time_ms
            length = self.player.length_ms
            self.time_label.config(text=format_time(position / 1000.0))
            if length > 0:
                self.duration_label.config(text=format_time(length / 1000.0))
                if not self._seeking:
                    self.seek.set(min(1000.0, position / length * 1000.0))
            self.play_button.config(text="Pause" if self.player.is_playing else "Play")
            if not self._volume_dragging:
                self.volume.set(self.player.get_volume())
        except Exception:
            pass
        self.root.after(250, self._tick)

    # ------------------------------------------------------------- helpers --

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _bind_keys(self) -> None:
        self.root.bind("<space>", lambda _e: self._key(self.toggle_play))
        self.root.bind("<Left>", lambda _e: self._key(lambda: self.execute(Command("seek_rel", -5.0))))
        self.root.bind("<Right>", lambda _e: self._key(lambda: self.execute(Command("seek_rel", 10.0))))
        self.root.bind("<Up>", lambda _e: self._key(lambda: self.execute(Command("volume_rel", 10.0))))
        self.root.bind("<Down>", lambda _e: self._key(lambda: self.execute(Command("volume_rel", -10.0))))
        self.root.bind("<m>", lambda _e: self._key(self.toggle_mute))
        self.root.bind("<f>", lambda _e: self._key(lambda: self.set_fullscreen(True)))
        self.root.bind("<r>", lambda _e: self._key(lambda: self.execute(Command("restart"))))
        self.root.bind("<s>", lambda _e: self._key(lambda: self.execute(Command("stop"))))
        self.root.bind("<o>", lambda _e: self._key(self.open_file))
        self.root.bind("<Escape>", lambda _e: self.set_fullscreen(False))

    def _key(self, action):
        widget = self.root.focus_get()
        if isinstance(widget, (tk.Entry, tk.Text)):
            return None
        action()
        return "break"

    def on_close(self) -> None:
        if self.listener is not None:
            self.listener.stop()
        self.player.release()
        self.root.destroy()
