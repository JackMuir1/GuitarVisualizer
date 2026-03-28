import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

RGBColor = tuple[int, int, int]
WHITE: RGBColor = (255, 255, 255)

_HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")

_DEFAULT_COLORS: dict[str, RGBColor] = {
    "C":  (255, 0,   0),
    "C#": (255, 69,  0),
    "D":  (255, 140, 0),
    "D#": (255, 215, 0),
    "E":  (154, 205, 50),
    "F":  (0,   200, 0),
    "F#": (0,   206, 209),
    "G":  (0,   191, 255),
    "G#": (30,  144, 255),
    "A":  (75,  0,   130),
    "A#": (138, 43,  226),
    "B":  (255, 0,   255),
}


class ColorMapper:
    def __init__(self, config: dict[str, Any]) -> None:
        self._mapping: dict[str, RGBColor] = dict(_DEFAULT_COLORS)
        self.update_config(config)

    def note_to_color(self, note: str) -> RGBColor:
        """Return the RGB color for a given note name."""
        return self._mapping.get(note, WHITE)

    def update_config(self, config: dict[str, Any]) -> None:
        """Reload note-color mapping from updated config."""
        raw_colors = config.get("note_colors", {})
        if not isinstance(raw_colors, dict):
            logger.warning("note_colors config is not a mapping; using defaults.")
            return

        new_mapping = dict(_DEFAULT_COLORS)
        for note, hex_str in raw_colors.items():
            if not isinstance(note, str) or not isinstance(hex_str, str):
                logger.warning("Skipping invalid note_colors entry: %r -> %r", note, hex_str)
                continue
            fallback = _DEFAULT_COLORS.get(note, WHITE)
            new_mapping[note] = self._parse_hex(hex_str, fallback)

        self._mapping = new_mapping

    def _parse_hex(self, hex_str: str, fallback: RGBColor) -> RGBColor:
        """Parse a #RRGGBB hex string to an RGB tuple; return fallback on error."""
        stripped = hex_str.strip()
        if not _HEX_PATTERN.match(stripped):
            logger.warning("Invalid hex color %r; using fallback %r.", hex_str, fallback)
            return fallback
        r = int(stripped[1:3], 16)
        g = int(stripped[3:5], 16)
        b = int(stripped[5:7], 16)
        return (r, g, b)


def lerp_color(current: RGBColor, target: RGBColor, speed: float) -> RGBColor:
    """Linearly interpolate between two RGB colors by `speed` (0.0–1.0)."""
    speed = max(0.0, min(1.0, speed))
    return (
        int(current[0] + (target[0] - current[0]) * speed),
        int(current[1] + (target[1] - current[1]) * speed),
        int(current[2] + (target[2] - current[2]) * speed),
    )
