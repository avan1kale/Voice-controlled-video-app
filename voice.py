"""Background speech recognition.

Runs in a daemon thread and posts events to a queue that the GUI polls:

    ("status", str)  what the listener is doing
    ("heard",  str)  a recognised phrase, ready to parse
    ("error",  str)  something went wrong, shown to the user

Two backends are supported (see config.py):
    "google"  online, free Web Speech API, needs internet, very accurate
    "vosk"    offline, needs the `vosk` package and a downloaded model
"""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Optional


class VoiceListener(threading.Thread):
    def __init__(
        self,
        out_queue: "queue.Queue[tuple[str, str]]",
        language: str = "en-IN",
        backend: str = "google",
        model_path: str = "",
        device_index: Optional[int] = None,
    ) -> None:
        super().__init__(daemon=True, name="voice-listener")
        self.out = out_queue
        self.language = language
        self.backend = backend
        self.model_path = model_path
        self.device_index = device_index
        self._stop_event = threading.Event()

    # -- public -------------------------------------------------------------

    def stop(self) -> None:
        self._stop_event.set()

    # -- thread body --------------------------------------------------------

    def run(self) -> None:
        try:
            import speech_recognition as sr
        except ImportError:
            self._emit(
                "error",
                "SpeechRecognition is not installed. Run: pip install SpeechRecognition",
            )
            return

        vosk_recogniser = None
        if self.backend == "vosk":
            vosk_recogniser = self._load_vosk()
            if vosk_recogniser is None:
                return

        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.6
        recognizer.non_speaking_duration = 0.4

        try:
            microphone = sr.Microphone(device_index=self.device_index)
        except Exception as exc:
            self._emit("error", f"No microphone available: {exc}")
            return

        self._emit("status", "Calibrating microphone, stay quiet for a second...")
        try:
            with microphone as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.8)
                self._emit("status", "Listening")
                while not self._stop_event.is_set():
                    try:
                        audio = recognizer.listen(
                            source, timeout=0.8, phrase_time_limit=6
                        )
                    except sr.WaitTimeoutError:
                        continue
                    except Exception as exc:
                        self._emit("error", f"Microphone error: {exc}")
                        return

                    if self.backend == "vosk":
                        text = self._transcribe_vosk(vosk_recogniser, audio)
                    else:
                        text = self._transcribe_google(sr, recognizer, audio)
                    if text:
                        self._emit("heard", text.strip())
        except Exception as exc:
            self._emit("error", f"Listening stopped: {exc}")
            return
        finally:
            self._emit("status", "Microphone off")

    # -- backends -----------------------------------------------------------

    def _transcribe_google(self, sr, recognizer, audio) -> Optional[str]:
        try:
            return recognizer.recognize_google(audio, language=self.language)
        except sr.UnknownValueError:
            return None  # silence or noise, not an error
        except sr.RequestError as exc:
            self._emit(
                "error",
                "Google speech service unreachable "
                f"({exc}). Check the internet, or set BACKEND = 'vosk' in config.py "
                "to work offline.",
            )
            return None
        except Exception as exc:
            self._emit("error", f"Transcription failed: {exc}")
            return None

    def _load_vosk(self):
        try:
            import vosk  # type: ignore
        except ImportError:
            self._emit("error", "vosk is not installed. Run: pip install vosk")
            return None
        if not self.model_path:
            self._emit(
                "error",
                "BACKEND is 'vosk' but VOSK_MODEL_PATH is empty. Set it in config.py.",
            )
            return None
        try:
            vosk.SetLogLevel(-1)
            model = vosk.Model(self.model_path)
        except Exception as exc:
            self._emit("error", f"Could not load the Vosk model: {exc}")
            return None
        return vosk.KaldiRecognizer(model, 16000)

    def _transcribe_vosk(self, recogniser, audio) -> Optional[str]:
        try:
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            recogniser.AcceptWaveform(raw)
            text = json.loads(recogniser.Result()).get("text", "")
            return text or None
        except Exception as exc:
            self._emit("error", f"Offline transcription failed: {exc}")
            return None

    # -- helpers ------------------------------------------------------------

    def _emit(self, kind: str, payload: str) -> None:
        self.out.put((kind, payload))
