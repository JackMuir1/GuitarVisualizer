import logging
import math
import threading
from typing import Any, Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Frequency bounds for guitar fundamentals (low E2 ~82 Hz, high E6 ~1319 Hz)
_MIN_FREQ_HZ = 60.0
_MAX_FREQ_HZ = 1400.0

# YIN threshold: lower = more selective, higher = more permissive
_YIN_THRESHOLD = 0.15


def yin_pitch(samples: np.ndarray, sample_rate: int, threshold: float) -> tuple[float, float]:
    """
    Estimate the fundamental frequency of a monophonic signal using the YIN algorithm.

    Returns (frequency_hz, confidence) where confidence is 0.0–1.0.
    Returns (0.0, 0.0) when no clear pitch is found.

    Reference: de Cheveigné & Kawahara, "YIN, a fundamental frequency estimator
    for speech and music", JASA 2002.
    """
    n = len(samples)
    half = n // 2

    # Step 1: Difference function
    # d(tau) = sum((x[j] - x[j+tau])^2) for j in [0, half)
    diff = np.zeros(half, dtype=np.float64)
    for tau in range(1, half):
        delta = samples[:half] - samples[tau: tau + half]
        diff[tau] = float(np.dot(delta, delta))

    # Step 2: Cumulative mean normalized difference function
    cmndf = np.zeros(half, dtype=np.float64)
    cmndf[0] = 1.0
    running_sum = 0.0
    for tau in range(1, half):
        running_sum += diff[tau]
        if running_sum == 0.0:
            cmndf[tau] = 1.0
        else:
            cmndf[tau] = diff[tau] * tau / running_sum

    # Step 3: Find the first tau where cmndf dips below threshold
    tau_min = _MIN_PERIOD(sample_rate)
    tau_max = _MAX_PERIOD(sample_rate, half)

    tau_est = 0
    for tau in range(tau_min, tau_max):
        if cmndf[tau] < threshold:
            # Keep going while still descending (find local minimum)
            while tau + 1 < tau_max and cmndf[tau + 1] < cmndf[tau]:
                tau += 1
            tau_est = tau
            break

    if tau_est == 0:
        return 0.0, 0.0

    # Step 4: Parabolic interpolation to refine the period estimate
    if 0 < tau_est < half - 1:
        s0 = cmndf[tau_est - 1]
        s1 = cmndf[tau_est]
        s2 = cmndf[tau_est + 1]
        denom = s0 - 2.0 * s1 + s2
        if denom != 0.0:
            tau_refined = tau_est + (s0 - s2) / (2.0 * denom)
        else:
            tau_refined = float(tau_est)
    else:
        tau_refined = float(tau_est)

    frequency = sample_rate / tau_refined
    confidence = max(0.0, 1.0 - cmndf[tau_est])
    return frequency, confidence


def _MIN_PERIOD(sample_rate: int) -> int:
    return max(2, int(sample_rate / _MAX_FREQ_HZ))


def _MAX_PERIOD(sample_rate: int, half: int) -> int:
    return min(half - 1, int(sample_rate / _MIN_FREQ_HZ) + 1)


class AudioEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        self._lock = threading.Lock()
        self._stream: Optional[sd.InputStream] = None

        self._current_note: Optional[str] = None
        self._amplitude_db: float = -80.0

        self._sample_rate: int = 44100
        self._buffer_size: int = 1024
        self._device: Optional[str | int] = None
        self._noise_gate_db: float = -20.0
        self._confidence_threshold: float = 0.6

        self.update_config(config)

    def start(self) -> None:
        """Open the audio stream and begin capturing."""
        device = self._resolve_device(self._device)
        self._open_stream(device)

    def stop(self) -> None:
        """Close the audio stream."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.warning("Error closing audio stream: %s", exc)
            finally:
                self._stream = None

    def get_current_note(self) -> Optional[str]:
        """Return the most recently detected note name, or None if silent."""
        with self._lock:
            return self._current_note

    def get_amplitude_db(self) -> float:
        """Return the current RMS amplitude in dBFS."""
        with self._lock:
            return self._amplitude_db

    def update_config(self, config: dict[str, Any]) -> None:
        """Apply updated config values (noise gate, confidence threshold)."""
        audio_cfg = config.get("audio", {})
        det_cfg = config.get("detection", {})

        self._sample_rate = int(audio_cfg.get("sample_rate", 44100))
        self._buffer_size = int(audio_cfg.get("buffer_size", 1024))
        self._device = audio_cfg.get("device", None)
        self._noise_gate_db = float(det_cfg.get("noise_gate_db", -20.0))
        self._confidence_threshold = float(det_cfg.get("confidence_threshold", 0.6))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open_stream(self, device: Optional[str | int]) -> None:
        try:
            self._stream = sd.InputStream(
                device=device,
                samplerate=self._sample_rate,
                blocksize=self._buffer_size,
                channels=1,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info(
                "Audio stream started — device=%r, rate=%d, buffer=%d",
                device, self._sample_rate, self._buffer_size,
            )
        except Exception as exc:
            logger.error("Failed to open audio device %r: %s", device, exc)
            if device is not None:
                logger.warning("Retrying with system default audio device.")
                self._open_stream(None)

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time: Any,
        status: sd.CallbackFlags,
    ) -> None:
        """sounddevice callback — runs on audio thread, must not block."""
        if status:
            logger.warning("Audio stream status: %s", status)

        # Validate buffer before any processing
        if not isinstance(indata, np.ndarray):
            return
        if indata.dtype != np.float32:
            return
        if indata.ndim != 2 or indata.shape[1] != 1:
            return
        if indata.shape[0] != self._buffer_size:
            return

        mono = indata[:, 0]

        # Guard against NaN/Inf from a misbehaving driver
        if not np.isfinite(mono).all():
            return

        amplitude_db = self._rms_to_db(mono)

        note: Optional[str] = None
        if amplitude_db >= self._noise_gate_db:
            freq, confidence = yin_pitch(
                mono.astype(np.float64), self._sample_rate, _YIN_THRESHOLD
            )
            if (
                confidence >= self._confidence_threshold
                and _MIN_FREQ_HZ <= freq <= _MAX_FREQ_HZ
            ):
                note = self._hz_to_note(freq)

        with self._lock:
            self._current_note = note
            self._amplitude_db = amplitude_db

    def _hz_to_note(self, frequency: float) -> Optional[str]:
        """Convert a frequency in Hz to a chromatic note name."""
        if frequency <= 0:
            return None
        midi = 12 * math.log2(frequency / 440.0) + 69
        note_index = int(round(midi)) % 12
        return NOTE_NAMES[note_index]

    @staticmethod
    def _rms_to_db(samples: np.ndarray) -> float:
        """Compute RMS amplitude in dBFS. Returns -80 for silence."""
        rms = float(np.sqrt(np.mean(samples ** 2)))
        if rms < 1e-10:
            return -80.0
        return max(-80.0, 20.0 * math.log10(rms))

    @staticmethod
    def _resolve_device(device: Optional[str | int]) -> Optional[str | int]:
        """Verify the requested device exists; return None (default) if not."""
        if device is None:
            return None
        try:
            sd.query_devices(device)
            return device
        except Exception:
            logger.warning("Audio device %r not found; falling back to system default.", device)
            return None
