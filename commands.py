"""Turn a spoken phrase into a player action.

Pure Python (no third-party imports), so the whole parser can be tested
without a microphone, a display or VLC.

    >>> parse_command("forward ten seconds")
    Command(action='seek_rel', value=10.0)
    >>> parse_command("jump to 1:30")
    Command(action='seek_to', value=90.0)
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

# Tunables. config.py overwrites these at start-up if the user changes them.
DEFAULT_FORWARD = 10.0
DEFAULT_REWIND = 10.0
VOLUME_STEP = 10
SPEED_LADDER = (0.5, 1.0, 1.5, 2.0)


@dataclass(frozen=True)
class Command:
    """One player action, ready to execute."""

    action: str
    value: Optional[float] = None


# --------------------------------------------------------------------------
# Numbers spoken as words
# --------------------------------------------------------------------------

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_NUMBER_WORDS = {**_UNITS, **_TENS}


def _token_value(token: str) -> Optional[float]:
    """Numeric value of one token, or None if it is not a number."""
    if token in _NUMBER_WORDS:
        return float(_NUMBER_WORDS[token])
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        return float(token)
    return None


def _fmt(value: float) -> str:
    return f"{value:g}"


def _digitise(text: str) -> str:
    """Replace spoken numbers with digits: 'twenty five seconds' -> '25 seconds'."""
    out: List[str] = []
    run: List[str] = []
    decimals: Optional[List[str]] = None

    def flush() -> None:
        nonlocal decimals
        if decimals is None:
            if run:
                out.append(_fmt(sum(_token_value(t) or 0.0 for t in run)))
            run.clear()
            return
        whole = sum(_token_value(t) or 0.0 for t in run) if run else 0.0
        frac = "".join(str(int(_token_value(d) or 0)) for d in decimals) or "0"
        out.append(f"{_fmt(whole)}.{frac}")
        run.clear()
        decimals = None

    for token in text.split():
        low = token.lower()
        if low == "point":
            decimals = []
            continue
        if _token_value(low) is not None:
            (decimals if decimals is not None else run).append(low)
            continue
        flush()
        out.append(token)
    flush()
    return " ".join(out)


# --------------------------------------------------------------------------
# Times and amounts
# --------------------------------------------------------------------------

_COLON_RE = re.compile(r"(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?")
_UNIT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|min|m|seconds?|secs?|sec|s)\b"
)


def parse_time(text: str) -> Optional[float]:
    """Seconds from a spoken time: '1:30', '2 minutes 10 seconds', '90', '1.5 min'."""
    spoken = _digitise(text.lower())

    match = _COLON_RE.search(spoken)
    if match:
        parts = [int(p) for p in match.groups() if p is not None]
        total = 0
        for part in parts:
            total = total * 60 + part
        return float(total)

    total = 0.0
    found = False
    last_end = 0
    for match in _UNIT_RE.finditer(spoken):
        number, unit = match.group(1), match.group(2)
        value = float(number)
        if unit.startswith("h"):
            value *= 3600
        elif unit.startswith("m"):
            value *= 60
        total += value
        found = True
        last_end = match.end()
    if found:
        # "1 minute 30" -> 90: a bare number after the last unit is seconds
        tail = re.search(r"\d+(?:\.\d+)?", spoken[last_end:])
        if tail:
            extra = float(tail.group())
            if extra < 60:
                total += extra
        return total

    match = re.search(r"\d+(?:\.\d+)?", spoken)
    return float(match.group()) if match else None


def _amount(text: str, default: float) -> float:
    """Amount in the phrase, understanding units: '1 minute' -> 60."""
    spoken = _digitise(text.lower())
    if _UNIT_RE.search(spoken) or _COLON_RE.search(spoken):
        value = parse_time(spoken)
        return default if value is None else value
    match = re.search(r"\d+(?:\.\d+)?", spoken)
    return float(match.group()) if match else default


# --------------------------------------------------------------------------
# Normalising what the recogniser heard
# --------------------------------------------------------------------------

_FILLERS = re.compile(r"\b(please|kindly|hey|okay|ok|um|uh|just|now)\b")


def _normalise(text: str) -> str:
    spoken = text.lower().strip()
    spoken = spoken.replace("full screen", "fullscreen")
    # Drop full stops and commas, but keep the dot in decimals like 1.5
    spoken = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", spoken)
    spoken = re.sub(r"[^\w\s:.]", " ", spoken)
    spoken = spoken.replace("un mute", "unmute").replace("re start", "restart")
    spoken = _FILLERS.sub(" ", spoken)
    return re.sub(r"\s+", " ", spoken).strip()


# --------------------------------------------------------------------------
# Rules, tried in order. The first one that matches wins.
# --------------------------------------------------------------------------

def _r_unmute(t: str) -> Optional[Command]:
    if re.search(r"\bunmute\b", t):
        return Command("unmute")
    if re.search(r"\b(sound|audio|volume)\b.*\bon\b", t) or re.search(r"\bturn\s+(the\s+)?sound\s+on\b", t):
        return Command("unmute")
    return None


def _r_mute(t: str) -> Optional[Command]:
    if re.search(r"\bmute\b", t) or re.search(r"\bsilence\b", t):
        return Command("mute")
    if re.search(r"\b(sound|audio)\s+(off|down)\b", t) or re.search(r"\bturn\s+(the\s+)?sound\s+off\b", t):
        return Command("mute")
    return None


def _r_windowed(t: str) -> Optional[Command]:
    if re.search(r"\b(exit|leave|close|out\s+of|stop)\s+(the\s+)?fullscreen\b", t):
        return Command("windowed")
    if re.search(r"\bwindow(ed)?\s*(mode|view|screen)?\b", t):
        return Command("windowed")
    return None


def _r_fullscreen(t: str) -> Optional[Command]:
    if re.search(r"\bfullscreen\b", t) or re.search(r"\bmaximi[sz]e\b", t):
        return Command("fullscreen")
    return None


def _r_stop(t: str) -> Optional[Command]:
    if re.search(r"\bstop\b", t):
        return Command("stop")
    return None


def _r_restart(t: str) -> Optional[Command]:
    if re.search(
        r"\b(restart|replay|start\s+over|start\s+again|from\s+the\s+(start|beginning)"
        r"|to\s+the\s+(start|beginning)|beginning)\b",
        t,
    ):
        return Command("restart")
    return None


def _r_speed(t: str) -> Optional[Command]:
    if re.search(r"\bfast\s*forward\b", t):
        return None  # that is a seek, not a speed change

    if re.search(r"\b(normal|regular|default)\s+speed\b", t):
        return Command("speed", 1.0)
    if re.search(r"\bhalf\s+speed\b", t):
        return Command("speed", 0.5)
    if re.search(r"\bdouble\s+speed\b", t):
        return Command("speed", 2.0)

    # Spoken numbers first: "one point five x" -> "1.5 x"
    spoken = _digitise(t)
    match = re.search(r"\b(?:speed|rate)\b[^\d]{0,12}(\d+(?:\.\d+)?)", spoken)
    if match:
        return Command("speed", float(match.group(1)))
    match = re.search(
        r"\b(?:play|run|watch)\b[^:]*?\bat\b[^\d]{0,12}(\d+(?:\.\d+)?)", spoken
    )
    if match:
        return Command("speed", float(match.group(1)))
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:x|times)\b", spoken)
    if match:
        return Command("speed", float(match.group(1)))

    if re.search(r"\b(slower|slow\s+down|speed\s+down|decrease\s+speed)\b", t):
        return Command("speed_step", -1.0)
    if re.search(r"\b(faster|speed\s+up|increase\s+speed)\b", t):
        return Command("speed_step", 1.0)
    return None


def _r_volume(t: str) -> Optional[Command]:
    spoken = _digitise(t)
    match = re.search(r"\b(?:set\s+)?(?:the\s+)?volume\s+(?:to\s+|at\s+)(\d{1,3})\b", spoken)
    if match:
        return Command("volume_set", float(match.group(1)))
    match = re.search(r"\bvolume\s+(\d{1,3})\b", spoken)
    if match:
        return Command("volume_set", float(match.group(1)))

    up = re.search(
        r"\b(volume\s+(up|higher|increase)|increase\s+(the\s+)?volume|louder"
        r"|turn\s+(it|the\s+volume)\s+up|turn\s+up\s+(the\s+)?volume)\b",
        t,
    )
    down = re.search(
        r"\b(volume\s+(down|lower|decrease)|decrease\s+(the\s+)?volume|quieter"
        r"|lower\s+(the\s+)?volume|turn\s+(it|the\s+volume)\s+down|turn\s+down\s+(the\s+)?volume)\b",
        t,
    )
    if up:
        return Command("volume_rel", +_amount(t, VOLUME_STEP))
    if down:
        return Command("volume_rel", -_amount(t, VOLUME_STEP))
    return None


def _r_rewind(t: str) -> Optional[Command]:
    if not re.search(r"\b(rewind|back|backwards?|reverse)\b", t):
        return None
    return Command("seek_rel", -_amount(t, DEFAULT_REWIND))


def _r_forward(t: str) -> Optional[Command]:
    if not re.search(r"\b(fast\s*forward|forward|ahead|advance|next)\b", t):
        return None
    return Command("seek_rel", _amount(t, DEFAULT_FORWARD))


_JUMP_RE = re.compile(
    r"\b(?:jump|seek|go|skip|move|take\s+me|play\s+from|start\s+at|resume\s+from|timestamp)\b(.*)$"
)


def _r_jump(t: str) -> Optional[Command]:
    match = _JUMP_RE.search(t)
    if not match:
        return None
    tail = match.group(1)
    if re.search(r"\b(back|backward|rewind|forward|ahead|behind)\b", tail):
        return None  # a relative seek, handled by the rules above
    seconds = parse_time(tail)
    if seconds is None:
        return None
    return Command("seek_to", seconds)


def _r_pause(t: str) -> Optional[Command]:
    if re.search(r"\bpause\b|\bfreeze\b|\bhold\b", t):
        return Command("pause")
    return None


def _r_play(t: str) -> Optional[Command]:
    if re.search(r"\b(play|resume|unpause|continue|start)\b", t):
        return Command("play")
    return None


def _r_open(t: str) -> Optional[Command]:
    if re.search(r"\b(open|load|browse|choose|select)\b", t):
        return Command("open")
    return None


def _r_quit(t: str) -> Optional[Command]:
    if re.search(r"\b(quit|exit|close)\b", t):
        return Command("quit")
    return None


_RULES: List[Callable[[str], Optional[Command]]] = [
    _r_unmute,
    _r_mute,
    _r_windowed,
    _r_fullscreen,
    _r_stop,
    _r_restart,
    _r_speed,
    _r_volume,
    _r_rewind,
    _r_forward,
    _r_jump,
    _r_pause,
    _r_play,
    _r_open,
    _r_quit,
]

# Short phrases a recogniser commonly mangles ("pause" -> "paws").
_FUZZY: dict = {
    "play": Command("play"),
    "pause": Command("pause"),
    "resume": Command("play"),
    "stop": Command("stop"),
    "mute": Command("mute"),
    "unmute": Command("unmute"),
    "restart": Command("restart"),
    "fullscreen": Command("fullscreen"),
    "volume up": Command("volume_rel", float(VOLUME_STEP)),
    "volume down": Command("volume_rel", -float(VOLUME_STEP)),
    "forward": Command("seek_rel", DEFAULT_FORWARD),
    "rewind": Command("seek_rel", -DEFAULT_REWIND),
    "faster": Command("speed_step", 1.0),
    "slower": Command("speed_step", -1.0),
    "normal speed": Command("speed", 1.0),
    "open file": Command("open"),
}


def _fuzzy(t: str) -> Optional[Command]:
    if len(t.split()) > 3:
        return None
    best, best_score = None, 0.0
    for phrase, command in _FUZZY.items():
        score = difflib.SequenceMatcher(None, t, phrase).ratio()
        if score > best_score:
            best, best_score = command, score
    return best if best_score >= 0.65 else None


def parse_command(text: str) -> Optional[Command]:
    """Parse one spoken phrase. Returns None when nothing matches."""
    if not text or not text.strip():
        return None
    spoken = _normalise(text)
    if not spoken:
        return None
    for rule in _RULES:
        command = rule(spoken)
        if command is not None:
            return command
    return _fuzzy(spoken)


# --------------------------------------------------------------------------
# Human-readable text for the UI log
# --------------------------------------------------------------------------

def format_time(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def describe(command: Command) -> str:
    action, value = command.action, command.value
    if action == "seek_rel" and value is not None:
        step = f"{abs(value):g}"
        return f"Forward {step} s" if value >= 0 else f"Rewind {step} s"
    if action == "seek_to" and value is not None:
        return f"Jump to {format_time(value)}"
    if action == "volume_rel" and value is not None:
        return f"Volume {'up' if value > 0 else 'down'} {abs(value):g}%"
    if action == "volume_set" and value is not None:
        return f"Volume {value:g}%"
    if action == "speed" and value is not None:
        return f"Speed {value:g}x"
    if action == "speed_step" and value is not None:
        return "Speed up" if value > 0 else "Slow down"
    return action.replace("_", " ").capitalize()


if __name__ == "__main__":  # quick manual check: python commands.py "forward 10 seconds"
    import sys

    phrase = " ".join(sys.argv[1:]) or "pause"
    parsed = parse_command(phrase)
    print(f"{phrase!r} -> {parsed}  ({describe(parsed) if parsed else 'no match'})")
