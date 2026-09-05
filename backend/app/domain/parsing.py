"""Script parsing (SPEC section 12).

Both parsers produce the same canonical output -- an ordered list of segments
-- so the rest of the system never sees raw markup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Sentence splitting must survive abbreviations, decimals and quotations, so a
# naive split on "." is explicitly ruled out by the SPEC. Rather than pull in a
# tokenizer, we split on terminal punctuation and then rejoin any break that
# landed after a known abbreviation or inside a number.
_ABBREVIATIONS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "st",
        "mt",
        "rev",
        "hon",
        "gen",
        "col",
        "lt",
        "sgt",
        "capt",
        "cmdr",
        "adm",
        "gov",
        "pres",
        "sen",
        "rep",
        "supt",
        "det",
        "insp",
        "messrs",
        "mmes",
        "msgr",
        "e.g",
        "i.e",
        "etc",
        "vs",
        "cf",
        "al",
        "approx",
        "dept",
        "est",
        "fig",
        "inc",
        "ltd",
        "co",
        "corp",
        "no",
        "vol",
        "pp",
        "ed",
        "eds",
        "trans",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
        "u.s",
        "u.k",
        "u.n",
        "e.u",
        "a.m",
        "p.m",
        "ph.d",
        "m.d",
        "b.a",
        "m.a",
    }
)

# A sentence ends at . ! or ? (possibly repeated, possibly followed by a
# closing quote or bracket) when the next character starts a new sentence.
_SENTENCE_END = re.compile(
    # Break after the closing quote/bracket when one follows the terminal
    # punctuation ('"Stop." She left.'), otherwise straight after it.
    r"""(?<=[.!?]["')\]])(?=\s)|(?<=[.!?])(?=\s)"""
)
_TRAILING_TOKEN = re.compile(r'([A-Za-z][A-Za-z.]*)\.["\')\]]?$')
_DIGIT_BEFORE_DOT = re.compile(r"\d\.$")

# [A] on its own line, then that speaker's lines until the next marker.
_BRACKET_SPEAKER = re.compile(r"^\s*\[([^\]\n]{1,40})\]\s*$")
# "A: text" on a single line. Prose routinely contains a colon ("There is one
# rule: never guess."), so the label has to be shaped like a name to count: it
# starts uppercase and is either one word, or a word followed by a short
# identifier such as "Speaker A" or "Person 1".
_INLINE_SPEAKER = re.compile(
    r"^\s*([A-Z][A-Za-z0-9_'.-]{0,19}(?:\s+[A-Z0-9][A-Za-z0-9'-]{0,9})?)\s*:\s+(\S.*)$"
)

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class ParsedSegment:
    order_index: int
    speaker_label: str | None
    text: str
    # True when this segment starts a new paragraph, so the render pipeline can
    # apply the longer paragraph pause instead of the sentence pause.
    starts_paragraph: bool = False


def _ends_with_abbreviation(chunk: str) -> bool:
    stripped = chunk.rstrip()
    if _DIGIT_BEFORE_DOT.search(stripped):
        return True
    match = _TRAILING_TOKEN.search(stripped)
    if not match:
        return False
    token = match.group(1).rstrip(".").lower()
    if token in _ABBREVIATIONS:
        return True
    # Single initials ("J. R. R. Tolkien") and dotted acronyms ("U.S.A.").
    return len(token) == 1 or ("." in token and len(token.replace(".", "")) <= 4)


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences, keeping abbreviations intact."""
    text = text.strip()
    if not text:
        return []

    pieces = _SENTENCE_END.split(text)
    sentences: list[str] = []
    buffer = ""
    for piece in pieces:
        buffer = f"{buffer}{piece}" if buffer else piece
        if _ends_with_abbreviation(buffer):
            continue
        cleaned = buffer.strip()
        if cleaned:
            sentences.append(cleaned)
        buffer = ""
    if buffer.strip():
        sentences.append(buffer.strip())
    return sentences


def parse_monologue(source_text: str) -> list[ParsedSegment]:
    segments: list[ParsedSegment] = []
    for paragraph in _PARAGRAPH_BREAK.split(source_text.strip()):
        if not paragraph.strip():
            continue
        for i, sentence in enumerate(split_sentences(paragraph)):
            segments.append(
                ParsedSegment(
                    order_index=len(segments),
                    speaker_label=None,
                    text=sentence,
                    starts_paragraph=(i == 0 and bool(segments)),
                )
            )
    return segments


def parse_dialogue(source_text: str) -> list[ParsedSegment]:
    """Parse `[A]` block form and `A: text` inline form into segments."""
    turns: list[tuple[str, list[str]]] = []
    current_label: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if current_label is not None and buffer:
            body = " ".join(line.strip() for line in buffer if line.strip())
            if body:
                turns.append((current_label, [body]))
        buffer = []

    for raw_line in source_text.splitlines():
        bracket = _BRACKET_SPEAKER.match(raw_line)
        if bracket:
            flush()
            current_label = bracket.group(1).strip()
            continue

        inline = _INLINE_SPEAKER.match(raw_line)
        if inline:
            flush()
            current_label = inline.group(1).strip()
            buffer = [inline.group(2)]
            flush()
            continue

        buffer.append(raw_line)
    flush()

    segments: list[ParsedSegment] = []
    for label, bodies in turns:
        for body in bodies:
            for sentence in split_sentences(body):
                segments.append(
                    ParsedSegment(
                        order_index=len(segments),
                        speaker_label=label,
                        text=sentence,
                    )
                )
    return segments


def parse_script(source_text: str, mode: str) -> list[ParsedSegment]:
    if mode == "dialogue":
        segments = parse_dialogue(source_text)
        # Fall back rather than returning nothing when the text carries no
        # speaker markup at all.
        if not segments:
            return parse_monologue(source_text)
        return segments
    return parse_monologue(source_text)


def speaker_labels(segments: list[ParsedSegment]) -> list[str]:
    """Distinct speaker labels in first-appearance order."""
    seen: dict[str, None] = {}
    for segment in segments:
        if segment.speaker_label is not None:
            seen.setdefault(segment.speaker_label, None)
    return list(seen)
