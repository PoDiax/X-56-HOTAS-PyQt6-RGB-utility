from __future__ import annotations

import colorsys
import math


EFFECT_OFF = "off"
EFFECT_RAINBOW = "rainbow"

EFFECT_MODES = [EFFECT_OFF, EFFECT_RAINBOW]


def compute_effect_color(
    mode: str,
    base_rgb: tuple[int, int, int],
    phase: float,
    brightness: float,
) -> tuple[int, int, int]:
    if mode == EFFECT_RAINBOW:
        hue = (phase / (2.0 * math.pi)) % 1.0
        red, green, blue = colorsys.hsv_to_rgb(hue, 1.0, max(0.05, min(1.0, brightness)))
        return (
            _clamp_rgb(round(red * 255.0)),
            _clamp_rgb(round(green * 255.0)),
            _clamp_rgb(round(blue * 255.0)),
        )

    return base_rgb


def next_phase(phase: float, speed: int) -> float:
    step = 0.02 * max(1, min(20, speed))
    return phase + step


def _clamp_rgb(value: int) -> int:
    return max(0, min(255, int(value)))
