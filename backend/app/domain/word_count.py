"""Counting words in a script.

Used for the word totals shown beside a script and printed on the transcript.
"""

from __future__ import annotations

import re

# A word is a run of letters/digits that may contain apostrophes or internal
# hyphens, so "don't" and "well-known" count once each. Standalone punctuation
# and the digits in "3.30" stay attached to their token rather than inflating
# the count.
_WORD = re.compile(r"[0-9A-Za-z]+(?:['’\-.][0-9A-Za-z]+)*")


def count_words(text: str) -> int:
    return len(_WORD.findall(text or ""))
