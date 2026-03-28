import logging
import time
from typing import Any, Optional

import pygame

from src.audio import AudioEngine
from src.color import ColorMapper, lerp_color, WHITE, RGBColor
from src.animation import AnimationEngine
from src.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class Visualizer:
    def __init__(
        self,
        config: dict[str, Any],
        audio_engine: AudioEngine,
        color_mapper: ColorMapper,
        animation_engine: AnimationEngine,
        config_loader: ConfigLoader,
    ) -> None:
        self._audio = audio_engine
        self._colors = color_mapper
        self._anim = animation_engine
        self._config_loader = config_loader

        self._current_color: RGBColor = WHITE
        self._target_color: RGBColor = WHITE
        self._last_note: Optional[str] = None
        self._last_note_time: float = time.monotonic()
        self._fading_to_white: bool = False

        self._fps: int = 60
        self._interp_speed: float = 0.05
        self._silence_timeout: float = 3.0
        self._silence_fade_speed: float = 0.002

        self._config_version: int = -1
        self._apply_display_config(config)

        self._screen: Optional[pygame.Surface] = None
        self._clock: Optional[pygame.time.Clock] = None

    def run(self) -> None:
        """Initialize pygame, start audio, and enter the main render loop."""
        pygame.init()
        info = pygame.display.Info()
        self._screen = pygame.display.set_mode(
            (info.current_w, info.current_h), pygame.FULLSCREEN | pygame.NOFRAME
        )
        pygame.display.set_caption("Guitar Visualizer")
        pygame.mouse.set_visible(False)
        self._clock = pygame.time.Clock()

        w, h = self._screen.get_size()
        self._anim.set_screen_size(w, h)

        self._audio.start()

        running = True
        try:
            while running:
                running = self._handle_events()
                self._sync_config()
                self._update()
                self._draw()
                self._clock.tick(self._fps)
        finally:
            self._shutdown()

    # ------------------------------------------------------------------
    # Loop internals
    # ------------------------------------------------------------------

    def _handle_events(self) -> bool:
        """Process pygame events; return False to signal quit."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    return False
        return True

    def _update(self) -> None:
        """Update color interpolation, silence fade, and animation state."""
        note = self._audio.get_current_note()
        amplitude_db = self._audio.get_amplitude_db()
        now = time.monotonic()

        if note is not None:
            self._last_note = note
            self._last_note_time = now
            self._fading_to_white = False
            self._target_color = self._colors.note_to_color(note)
        else:
            silence_duration = now - self._last_note_time
            if silence_duration >= self._silence_timeout:
                self._fading_to_white = True

        if self._fading_to_white:
            self._current_color = lerp_color(self._current_color, WHITE, self._silence_fade_speed)
        else:
            self._current_color = lerp_color(self._current_color, self._target_color, self._interp_speed)

        self._anim.update(amplitude_db, self._current_color)

    def _draw(self) -> None:
        """Fill background with current color and draw animation layer."""
        if self._screen is None:
            return
        self._screen.fill(self._current_color)
        self._anim.draw(self._screen)
        pygame.display.flip()

    def _sync_config(self) -> None:
        """Check for config reload and propagate updated values to all engines."""
        version = self._config_loader.get_version()
        if version == self._config_version:
            return

        config = self._config_loader.get()
        self._apply_display_config(config)
        self._audio.update_config(config)
        self._colors.update_config(config)
        self._anim.update_config(config)
        self._config_version = version
        logger.info("All engines updated from new config (version %d).", version)

    def _apply_display_config(self, config: dict[str, Any]) -> None:
        display = config.get("display", {})
        self._fps = int(display.get("fps", 60))
        self._interp_speed = float(display.get("interpolation_speed", 0.05))
        self._silence_timeout = float(display.get("silence_timeout_sec", 3.0))
        self._silence_fade_speed = float(display.get("silence_fade_speed", 0.002))

    def _shutdown(self) -> None:
        """Stop audio, file watcher, and pygame cleanly."""
        logger.info("Shutting down.")
        self._audio.stop()
        self._config_loader.stop()
        pygame.quit()
