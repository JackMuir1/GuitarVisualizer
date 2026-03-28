import logging
import math
import random
from dataclasses import dataclass
from typing import Any

import pygame

logger = logging.getLogger(__name__)

# Frutiger Aero palette: soft, glossy bubble overlays
_BUBBLE_BASE_ALPHA = 40
_BUBBLE_ALPHA_RANGE = 30


@dataclass
class Bubble:
    x: float
    y: float
    radius: float
    speed_x: float
    speed_y: float
    alpha: int
    phase: float          # offset into the pulse oscillation cycle
    phase_speed: float    # how fast this bubble pulses


class AnimationEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        self._screen_w: int = 0
        self._screen_h: int = 0
        self._bubbles: list[Bubble] = []

        self._bubble_count: int = 12
        self._min_radius: float = 30.0
        self._max_radius: float = 120.0
        self._amplitude_scale: float = 1.0

        # Current normalized amplitude (0.0 = silence, 1.0 = loud)
        self._amplitude_norm: float = 0.0

        self.update_config(config)

    def set_screen_size(self, width: int, height: int) -> None:
        """Must be called once after pygame display is initialized."""
        self._screen_w = width
        self._screen_h = height
        self._bubbles = [self._spawn_bubble() for _ in range(self._bubble_count)]

    def update(self, amplitude_db: float, base_color: tuple[int, int, int]) -> None:
        """Advance animation state one frame based on current amplitude."""
        self._amplitude_norm = self._amplitude_to_scale(amplitude_db)

        # Scale bubble speed and pulse with amplitude
        energy = self._amplitude_norm * self._amplitude_scale
        base_speed = 0.3 + energy * 1.2       # 0.3 (quiet) → 1.5 (loud)
        pulse_speed = 0.005 + energy * 0.03   # slow breathe → fast pulse

        for bubble in self._bubbles:
            bubble.x += bubble.speed_x * base_speed
            bubble.y += bubble.speed_y * base_speed
            bubble.phase = (bubble.phase + pulse_speed * bubble.phase_speed) % (2 * math.pi)

            # Wrap bubbles that drift off-screen
            if bubble.x < -bubble.radius:
                bubble.x = self._screen_w + bubble.radius
            elif bubble.x > self._screen_w + bubble.radius:
                bubble.x = -bubble.radius
            if bubble.y < -bubble.radius:
                bubble.y = self._screen_h + bubble.radius
            elif bubble.y > self._screen_h + bubble.radius:
                bubble.y = -bubble.radius

    def draw(self, surface: pygame.Surface) -> None:
        """Render all bubbles onto the given surface using additive blending."""
        if self._screen_w == 0 or self._screen_h == 0:
            return

        energy = self._amplitude_norm * self._amplitude_scale

        for bubble in self._bubbles:
            pulse = math.sin(bubble.phase)  # -1 → 1
            # Radius grows slightly with amplitude and pulse
            r = bubble.radius * (1.0 + 0.15 * pulse + 0.25 * energy)
            r = max(1.0, r)

            # Alpha modulates with pulse and amplitude
            alpha = int(bubble.alpha + _BUBBLE_ALPHA_RANGE * (0.5 + 0.5 * pulse + 0.3 * energy))
            alpha = max(10, min(180, alpha))

            self._draw_bubble(surface, bubble.x, bubble.y, r, alpha)

    def update_config(self, config: dict[str, Any]) -> None:
        """Apply updated animation config values."""
        anim = config.get("animation", {})
        new_count = int(anim.get("bubble_count", 12))
        self._min_radius = float(anim.get("bubble_min_radius", 30))
        self._max_radius = float(anim.get("bubble_max_radius", 120))
        self._amplitude_scale = float(anim.get("amplitude_scale", 1.0))

        # Grow or shrink bubble list to match new count
        while len(self._bubbles) < new_count:
            self._bubbles.append(self._spawn_bubble())
        self._bubbles = self._bubbles[:new_count]
        self._bubble_count = new_count

    def _spawn_bubble(self) -> Bubble:
        """Create a new bubble with randomized initial state."""
        w = max(self._screen_w, 100)
        h = max(self._screen_h, 100)
        radius = random.uniform(self._min_radius, self._max_radius)
        speed = random.uniform(0.2, 0.8)
        angle = random.uniform(0, 2 * math.pi)
        return Bubble(
            x=random.uniform(0, w),
            y=random.uniform(0, h),
            radius=radius,
            speed_x=math.cos(angle) * speed,
            speed_y=math.sin(angle) * speed,
            alpha=random.randint(_BUBBLE_BASE_ALPHA, _BUBBLE_BASE_ALPHA + _BUBBLE_ALPHA_RANGE),
            phase=random.uniform(0, 2 * math.pi),
            phase_speed=random.uniform(0.5, 2.0),
        )

    @staticmethod
    def _amplitude_to_scale(amplitude_db: float) -> float:
        """Map a dBFS value to a normalized 0.0–1.0 animation scale."""
        # Map -60 dB → 0.0, -10 dB → 1.0
        clamped = max(-60.0, min(-10.0, amplitude_db))
        return (clamped - (-60.0)) / (-10.0 - (-60.0))

    @staticmethod
    def _draw_bubble(
        surface: pygame.Surface,
        x: float,
        y: float,
        radius: float,
        alpha: int,
    ) -> None:
        """Draw a single glossy translucent bubble onto the surface."""
        r = int(radius)
        if r < 1:
            return

        # Render onto a temporary per-bubble surface for alpha blending
        bubble_surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)

        # Outer glow — soft, large, low alpha
        pygame.draw.circle(
            bubble_surf, (255, 255, 255, max(0, alpha // 3)), (r, r), r
        )
        # Main body — slightly smaller, semi-transparent
        pygame.draw.circle(
            bubble_surf, (255, 255, 255, alpha), (r, r), int(r * 0.85)
        )
        # Specular highlight — small bright spot (top-left quarter)
        highlight_r = max(1, int(r * 0.35))
        highlight_offset = int(r * 0.28)
        pygame.draw.circle(
            bubble_surf,
            (255, 255, 255, min(255, alpha * 3)),
            (r - highlight_offset, r - highlight_offset),
            highlight_r,
        )

        surface.blit(bubble_surf, (int(x) - r, int(y) - r), special_flags=pygame.BLEND_RGBA_ADD)
