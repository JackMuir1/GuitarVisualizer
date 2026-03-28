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


def yin_pitch(samples: np.ndarray, sample_rate: int, threshold: float) -> tuple[float, float]:
    """
    Estimate the fundamental frequency of a monophonic signal using the YIN algorithm.

    Returns (frequency_hz, confidence) where confidence is 0.0–1.0.
    Returns (0.0, 0.0) when no clear pitch is found.

    Fully vectorized using FFT-based cross-correlation for low-latency real-time use.

    Reference: de Cheveigné & Kawahara, "YIN, a fundamental frequency estimator
    for speech and music", JASA 2002.
    """
    n = len(samples)
    half = n // 2
    x = samples.astype(np.float64)
    w = half  # analysis window size

    # --- Step 1: Difference function (vectorized via FFT cross-correlation) ---
    # d[tau] = sum_{j=0}^{w-1} (x[j] - x[j+tau])^2
    #        = sum(x[:w]^2) + sum(x[tau:tau+w]^2) - 2 * cross[tau]
    # where cross[tau] = sum_j x[:w][j] * x[j+tau]

    fft_size = 1 << (n + w - 1).bit_length()
    Xa = np.fft.rfft(x[:w], n=fft_size)
    Xb = np.fft.rfft(x, n=fft_size)
    cross = np.fft.irfft(np.conj(Xa) * Xb)[:half]

    sq_cumsum = np.empty(n + 1, dtype=np.float64)
    sq_cumsum[0] = 0.0
    np.cumsum(x ** 2, out=sq_cumsum[1:])

    tau_arr = np.arange(half, dtype=np.int64)
    end_arr = np.minimum(tau_arr + w, n)
    sum_sq_tau = sq_cumsum[end_arr] - sq_cumsum[tau_arr]
    sum_sq_0 = sq_cumsum[w]

    diff = np.maximum(0.0, sum_sq_0 + sum_sq_tau - 2.0 * cross)
    diff[0] = 0.0

    # --- Step 2: Cumulative mean normalized difference (vectorized) ---
    cum_diff = np.cumsum(diff)
    taus_f = np.arange(half, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        cmndf = np.where(cum_diff > 0.0, diff * taus_f / cum_diff, 1.0)
    cmndf[0] = 1.0

    # --- Step 3: Find first tau below threshold in valid frequency range ---
    tau_min = max(2, int(sample_rate / _MAX_FREQ_HZ))
    tau_max = min(half - 1, int(sample_rate / _MIN_FREQ_HZ) + 1)

    below = np.where(cmndf[tau_min:tau_max] < threshold)[0]
    if len(below) == 0:
        return 0.0, 0.0

    tau = int(below[0]) + tau_min
    # Walk to the local minimum
    while tau + 1 < tau_max and cmndf[tau + 1] < cmndf[tau]:
        tau += 1
    tau_est = tau

    # --- Step 4: Parabolic interpolation ---
    if 0 < tau_est < half - 1:
        s0 = float(cmndf[tau_est - 1])
        s1 = float(cmndf[tau_est])
        s2 = float(cmndf[tau_est + 1])
        denom = s0 - 2.0 * s1 + s2
        if denom > 1e-10:
            correction = max(-0.5, min(0.5, (s0 - s2) / (2.0 * denom)))
            tau_refined = float(tau_est) + correction
        else:
            tau_refined = float(tau_est)
    else:
        tau_refined = float(tau_est)

    frequency = float(sample_rate) / max(tau_refined, 1.0)
    confidence = max(0.0, 1.0 - float(cmndf[tau_est]))
    return frequency, confidence


class AudioEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        self._lock = threading.Lock()
        self._stream: Optional[sd.InputStream] = None

        self._current_note: Optional[str] = None
        self._amplitude_db: float = -80.0
        self._last_logged_note: Optional[str] = None

        self._sample_rate: int = 44100
        self._buffer_size: int = 1024
        self._device: Optional[str | int] = None
        self._noise_gate_db: float = -20.0
        self._confidence_threshold: float = 0.6
        self._yin_threshold: float = 0.15

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
        """Apply updated config values."""
        audio_cfg = config.get("audio", {})
        det_cfg = config.get("detection", {})

        self._sample_rate = int(audio_cfg.get("sample_rate", 44100))
        self._buffer_size = int(audio_cfg.get("buffer_size", 1024))
        self._device = audio_cfg.get("device", None)
        self._noise_gate_db = float(det_cfg.get("noise_gate_db", -20.0))
        self._confidence_threshold = float(det_cfg.get("confidence_threshold", 0.6))
        self._yin_threshold = float(det_cfg.get("yin_threshold", 0.15))

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
        freq: float = 0.0
        confidence: float = 0.0

        if amplitude_db >= self._noise_gate_db:
            freq, confidence = yin_pitch(
                mono.astype(np.float64), self._sample_rate, self._yin_threshold
            )
            logger.debug(
                "YIN: amp=%.1f dB  freq=%.1f Hz  conf=%.2f", amplitude_db, freq, confidence
            )
            if (
                confidence >= self._confidence_threshold
                and _MIN_FREQ_HZ <= freq <= _MAX_FREQ_HZ
            ):
                note = self._hz_to_note(freq)

        # Log note changes at INFO so they're visible in the console by default
        if note != self._last_logged_note:
            logger.info(
                "Note: %s → %s  (%.1f Hz, conf=%.2f, amp=%.1f dB)",
                self._last_logged_note, note, freq, confidence, amplitude_db,
            )
            self._last_logged_note = note

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
