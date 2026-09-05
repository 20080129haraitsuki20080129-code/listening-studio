"""Generation-speed presets, labelled by words per minute.

A raw multiplier means nothing to someone building listening material; a pace
in words per minute does. These bands are measured, not assumed: SPEC section
11 is explicit that provider differences make WPM something you measure.

Measured on Kokoro with two voices (af_heart, bm_george) over a 47-word
passage. The ranges bracket both voices with a little margin, because voices
differ by a few words per minute at the same multiplier.

The scale stops at 1.30. Above it Kokoro's pace jumps discontinuously --
1.30 gives ~176 wpm and 1.40 ~213 -- so a level there would not sit evenly
between its neighbours.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeedLevel:
    level: int
    speed: float
    wpm_min: int
    wpm_max: int

    @property
    def wpm_label(self) -> str:
        return f"{self.wpm_min}-{self.wpm_max} wpm"


# level, speed, wpm_min, wpm_max
SPEED_LEVELS: tuple[SpeedLevel, ...] = (
    SpeedLevel(1, 0.70, 95, 105),
    SpeedLevel(2, 0.80, 105, 125),
    SpeedLevel(3, 0.90, 125, 140),
    SpeedLevel(4, 1.00, 140, 150),
    SpeedLevel(5, 1.10, 150, 160),
    SpeedLevel(6, 1.20, 160, 170),
    SpeedLevel(7, 1.30, 170, 185),
)

DEFAULT_LEVEL = 4


def level_for_speed(speed: float) -> SpeedLevel:
    """The preset closest to a stored speed.

    Projects store a multiplier, so a value saved before these presets existed
    still maps onto the nearest level rather than leaving the control blank.
    """
    return min(SPEED_LEVELS, key=lambda entry: abs(entry.speed - float(speed)))


def speed_for_level(level: int) -> float:
    for entry in SPEED_LEVELS:
        if entry.level == level:
            return entry.speed
    raise ValueError(f"Unknown speed level: {level}")
