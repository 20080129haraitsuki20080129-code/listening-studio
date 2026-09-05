"""Generation-speed presets, anchored to real listening material.

A raw multiplier means nothing to someone building material; a pace does. The
scale is anchored at two familiar points:

* level 4, the default, sits at roughly the pace of a Japanese university
  entrance-exam listening section (the University of Tokyo's is commonly put
  at about 150 words per minute);
* level 6 sits at roughly native news-broadcast pace, commonly put at 160-180;
* level 7 sits at the pace of a heated native argument, commonly put above 200.

Those reference figures are widely cited approximations, not published
standards, so they are presented as "about".

Everything below is measured, not assumed -- SPEC section 11 is explicit that
provider differences make WPM something you measure. Timings come from a
127-word passage read by four Kokoro voices (af_heart, bm_george, bf_emma,
am_adam), synthesized one sentence at a time exactly as the render pipeline
does.

Two things that measurement showed, which shape the scale:

* Kokoro's pace is not linear in the multiplier, so the multipliers are not
  evenly spaced -- they were picked so the resulting *pace* lands where it
  should. Pace also steps up sharply between 1.30 and 1.34 (175 to 203 wpm),
  which is why the gap from level 6 to 7 is the widest: no multiplier
  produces the ~190 wpm in between.
* Voices differ by around 20 wpm at the same multiplier, which is more than
  the gap between neighbouring levels. A level therefore advertises a typical
  pace and the observed spread, and the app reports the *actual* rate once a
  project has been rendered.
* Very short passages come out slower than the label. Each utterance carries
  fixed overhead -- leading and trailing silence, sentence-final lengthening
  -- and with few words there is little to amortize it over. Measured at
  multiplier 1.00: 9 words gives 127 wpm, 29 words 142, and it is flat from
  there through 127 words. So the labels describe passages of roughly a
  sentence or two upward, which is what listening material actually is, and
  the reported actual rate covers the rest.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeedLevel:
    level: int
    speed: float
    #: Mean across the four measured voices.
    wpm_typical: int
    #: Slowest and fastest of those voices at this multiplier.
    wpm_min: int
    wpm_max: int
    #: Anchor this level is calibrated to, if any. A translation key.
    reference: str | None = None


# Multipliers are not evenly spaced: they were chosen so the *pace* lands on
# the anchors, and Kokoro's response to the multiplier is not linear.
SPEED_LEVELS: tuple[SpeedLevel, ...] = (
    SpeedLevel(1, 0.76, 105, 96, 110),
    SpeedLevel(2, 0.84, 124, 111, 131),
    SpeedLevel(3, 0.92, 135, 121, 142),
    SpeedLevel(4, 1.08, 150, 136, 156, reference="exam"),
    SpeedLevel(5, 1.16, 158, 143, 165),
    SpeedLevel(6, 1.30, 175, 162, 183, reference="news"),
    SpeedLevel(7, 1.34, 203, 181, 214, reference="argument"),
)

DEFAULT_LEVEL = 4


def level_for_speed(speed: float) -> SpeedLevel:
    """The preset closest to a stored speed.

    Projects store a multiplier, so a value saved under an older scale still
    maps onto a level rather than leaving the control blank. A multiplier
    exactly between two levels resolves to the slower one: erring towards the
    easier pace is the kinder default for a listener.
    """
    target = float(speed)
    return min(
        SPEED_LEVELS,
        key=lambda entry: (abs(entry.speed - target), entry.level),
    )


def speed_for_level(level: int) -> float:
    for entry in SPEED_LEVELS:
        if entry.level == level:
            return entry.speed
    raise ValueError(f"Unknown speed level: {level}")


def measured_wpm(word_count: int, speech_ms: int) -> float | None:
    """Words per minute actually achieved.

    `speech_ms` is the summed length of the rendered segments, so it excludes
    the pauses between them and any repeat gaps. Those are silence, and
    counting them would understate how fast the voice is speaking.
    """
    if word_count <= 0 or speech_ms <= 0:
        return None
    return word_count / (speech_ms / 60_000)
