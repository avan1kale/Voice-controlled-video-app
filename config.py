"""Settings for the voice-controlled video player. Edit this file, not the code.

Everything here is read once at start-up.
"""

# ---------------------------------------------------------------- speech ----
# Language passed to the recogniser. en-IN suits Indian English.
LANGUAGE = "en-IN"

# "google" -> online, accurate, needs internet (free Web Speech API)
# "vosk"   -> offline, needs `pip install vosk` and a downloaded model
BACKEND = "google"

# Only used when BACKEND == "vosk". Folder you unzipped the model into, e.g.
#   Windows: r"C:\models\vosk-model-small-en-in-0.22"
#   Linux/macOS: "/home/you/models/vosk-model-small-en-in-0.22"
VOSK_MODEL_PATH = ""

# Optional wake word. "" acts on every phrase; "player" obeys only phrases
# that contain the word "player" (useful with speakers, not headphones).
WAKE_WORD = ""

# Microphone index. None = system default. To list devices:
#   python -m speech_recognition
MIC_DEVICE_INDEX = None

# -------------------------------------------------------------- playback ----
FORWARD_SECONDS = 10.0     # "forward" with no number
REWIND_SECONDS = 10.0      # "rewind" with no number
VOLUME_STEP = 10           # "volume up" with no number
SPEED_LADDER = (0.5, 1.0, 1.5, 2.0)   # ladder used by "faster" / "slower"

# ------------------------------------------------------------- applying ----
# commands.py owns the defaults; overriding them here keeps one source of truth.
import commands as _commands

_commands.DEFAULT_FORWARD = FORWARD_SECONDS
_commands.DEFAULT_REWIND = REWIND_SECONDS
_commands.VOLUME_STEP = VOLUME_STEP
_commands.SPEED_LADDER = SPEED_LADDER
