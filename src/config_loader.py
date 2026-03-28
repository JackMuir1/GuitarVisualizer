import logging
import threading
from pathlib import Path
from typing import Any

import yaml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

logger = logging.getLogger(__name__)

# Allowed top-level config keys — reject anything unexpected
_VALID_TOP_KEYS = {"audio", "detection", "display", "animation", "note_colors"}

# Numeric bounds for known scalar fields: key_path -> (min, max)
_NUMERIC_BOUNDS: dict[str, tuple[float, float]] = {
    "audio.sample_rate":          (8000,   192000),
    "audio.buffer_size":          (256,    8192),
    "detection.noise_gate_db":    (-80.0,  0.0),
    "detection.confidence_threshold": (0.0, 1.0),
    "display.fps":                (10,     240),
    "display.interpolation_speed":(0.001,  1.0),
    "display.silence_timeout_sec":(0.1,    60.0),
    "display.silence_fade_speed": (0.0001, 1.0),
    "animation.bubble_count":     (0,      100),
    "animation.bubble_min_radius":(1,      500),
    "animation.bubble_max_radius":(1,      500),
    "animation.amplitude_scale":  (0.0,    10.0),
}

DEFAULTS: dict[str, Any] = {
    "audio": {
        "device": None,
        "sample_rate": 44100,
        "buffer_size": 1024,
    },
    "detection": {
        "noise_gate_db": -20.0,
        "confidence_threshold": 0.6,
    },
    "display": {
        "fps": 60,
        "interpolation_speed": 0.05,
        "silence_timeout_sec": 3.0,
        "silence_fade_speed": 0.002,
    },
    "animation": {
        "bubble_count": 12,
        "bubble_min_radius": 30,
        "bubble_max_radius": 120,
        "amplitude_scale": 1.0,
    },
    "note_colors": {
        "C":  "#FF0000",
        "C#": "#FF4500",
        "D":  "#FF8C00",
        "D#": "#FFD700",
        "E":  "#9ACD32",
        "F":  "#00C800",
        "F#": "#00CED1",
        "G":  "#00BFFF",
        "G#": "#1E90FF",
        "A":  "#4B0082",
        "A#": "#8A2BE2",
        "B":  "#FF00FF",
    },
}


class _ConfigFileHandler(FileSystemEventHandler):
    def __init__(self, loader: "ConfigLoader") -> None:
        self._loader = loader

    def on_modified(self, event: FileModifiedEvent) -> None:
        if Path(event.src_path).resolve() == self._loader.config_path.resolve():
            self._loader.reload()


class ConfigLoader:
    def __init__(self, config_path: str) -> None:
        self.config_path = Path(config_path).resolve()
        self._lock = threading.Lock()
        self._config: dict[str, Any] = _deep_merge(DEFAULTS, {})
        self._observer: Observer | None = None
        self._version: int = 0

        self.reload()
        self._start_watching()

    def get(self) -> dict[str, Any]:
        """Return a shallow copy of the current config dict."""
        with self._lock:
            return dict(self._config)

    def get_version(self) -> int:
        """Return a counter that increments on every successful reload."""
        with self._lock:
            return self._version

    def reload(self) -> None:
        """Re-read and validate config.yaml; keep previous config on any error."""
        try:
            raw = self._read_file()
            parsed = self._parse(raw)
            validated = self._validate(parsed)
            merged = _deep_merge(DEFAULTS, validated)
            with self._lock:
                self._config = merged
                self._version += 1
            logger.info("Config reloaded successfully.")
        except Exception as exc:
            logger.error("Config reload failed — keeping previous config: %s", exc)

    def stop(self) -> None:
        """Stop the file watcher."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_file(self) -> str:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        # Limit file size to 64 KB — reject suspiciously large configs
        size = self.config_path.stat().st_size
        if size > 65536:
            raise ValueError(f"Config file too large ({size} bytes); refusing to parse.")
        return self.config_path.read_text(encoding="utf-8")

    def _parse(self, raw: str) -> dict[str, Any]:
        # safe_load prevents arbitrary Python object deserialization
        result = yaml.safe_load(raw)
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise TypeError("Config root must be a YAML mapping.")
        return result

    def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        # Reject unexpected top-level keys
        unknown = set(data.keys()) - _VALID_TOP_KEYS
        if unknown:
            logger.warning("Unknown config keys ignored: %s", unknown)
            data = {k: v for k, v in data.items() if k in _VALID_TOP_KEYS}

        # Clamp numeric values to safe bounds
        for key_path, (lo, hi) in _NUMERIC_BOUNDS.items():
            section, field = key_path.split(".", 1)
            if section in data and isinstance(data[section], dict):
                raw_val = data[section].get(field)
                if raw_val is not None:
                    if not isinstance(raw_val, (int, float)):
                        logger.warning(
                            "Config %s must be numeric; using default.", key_path
                        )
                        del data[section][field]
                    else:
                        clamped = max(lo, min(hi, raw_val))
                        if clamped != raw_val:
                            logger.warning(
                                "Config %s=%s out of range [%s, %s]; clamped to %s.",
                                key_path, raw_val, lo, hi, clamped,
                            )
                        data[section][field] = clamped

        # Validate note_colors: must be a dict of string -> string values
        if "note_colors" in data:
            nc = data["note_colors"]
            if not isinstance(nc, dict):
                logger.warning("note_colors must be a mapping; using defaults.")
                del data["note_colors"]
            else:
                safe_nc: dict[str, Any] = {}
                for note, color in nc.items():
                    if not isinstance(note, str) or not isinstance(color, str):
                        logger.warning("Skipping invalid note_colors entry: %r -> %r", note, color)
                        continue
                    safe_nc[str(note)] = str(color)
                data["note_colors"] = safe_nc

        # audio.device may be null (None) or a string/int — reject anything else
        if "audio" in data and isinstance(data["audio"], dict):
            device = data["audio"].get("device")
            if device is not None and not isinstance(device, (str, int)):
                logger.warning("audio.device must be null, a string, or an integer; using null.")
                data["audio"]["device"] = None

        return data

    def _start_watching(self) -> None:
        handler = _ConfigFileHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.config_path.parent), recursive=False)
        self._observer.daemon = True
        self._observer.start()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict merging override into base, recursively for nested dicts."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
