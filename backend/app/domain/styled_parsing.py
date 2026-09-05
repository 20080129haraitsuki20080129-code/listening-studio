"""Parsing a dialogue whose speakers are distinguished by text styling.

Typing [A] / [B] markers is tedious, so a turn can instead be marked with the
same bold / italic / underline a word processor uses. Three independent marks
give exactly eight combinations, which is where the eight-speaker ceiling comes
from.

Styling is read per line rather than per character: people format whole turns,
and a line-level reading means a stray bold word inside a sentence cannot split
one turn across two speakers.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

BOLD = 1
ITALIC = 2
UNDERLINE = 4

# The order the user picks voices in: plain, then single marks, then pairs,
# then all three. Voice 1 is always unstyled, Voice 2 always bold, and so on,
# so the mapping never shifts as a script is edited.
SLOT_ORDER: tuple[int, ...] = (
    0,
    BOLD,
    ITALIC,
    UNDERLINE,
    BOLD | ITALIC,
    BOLD | UNDERLINE,
    ITALIC | UNDERLINE,
    BOLD | ITALIC | UNDERLINE,
)
MAX_STYLE_SPEAKERS = len(SLOT_ORDER)

STYLE_NAMES: dict[int, str] = {
    0: "plain",
    BOLD: "bold",
    ITALIC: "italic",
    UNDERLINE: "underline",
    BOLD | ITALIC: "bold_italic",
    BOLD | UNDERLINE: "bold_underline",
    ITALIC | UNDERLINE: "italic_underline",
    BOLD | ITALIC | UNDERLINE: "bold_italic_underline",
}

_TAG_STYLES = {
    "b": BOLD,
    "strong": BOLD,
    "i": ITALIC,
    "em": ITALIC,
    "u": UNDERLINE,
    "ins": UNDERLINE,
}

# contenteditable emits these to separate lines.
_BLOCK_TAGS = frozenset(
    {"div", "p", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
)


def slot_index(mask: int) -> int:
    """Which voice slot a style combination belongs to (0-based)."""
    return SLOT_ORDER.index(mask)


def speaker_label_for_mask(mask: int) -> str:
    return chr(ord("A") + slot_index(mask))


def mask_for_label(label: str) -> int | None:
    index = ord(label) - ord("A")
    if 0 <= index < len(SLOT_ORDER):
        return SLOT_ORDER[index]
    return None


def _mask_from_style_attribute(value: str) -> int:
    """Read styling from an inline `style` attribute.

    Browsers do not agree on how they mark up formatted text -- some emit <b>,
    others a span with font-weight -- so both forms have to be understood.
    """
    mask = 0
    declarations = value.lower()
    if "font-weight" in declarations and (
        "bold" in declarations
        or any(
            f"font-weight:{n}" in declarations.replace(" ", "")
            for n in ("600", "700", "800", "900")
        )
    ):
        mask |= BOLD
    if "font-style" in declarations and "italic" in declarations:
        mask |= ITALIC
    if "text-decoration" in declarations and "underline" in declarations:
        mask |= UNDERLINE
    return mask


@dataclass
class StyledRun:
    mask: int
    text: str


class _StyledLineExtractor(HTMLParser):
    """Flatten styled HTML into lines of (style mask, text) runs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[list[StyledRun]] = [[]]
        self._stack: list[int] = []
        self.saw_styling = False

    # -- state --------------------------------------------------------------

    @property
    def _mask(self) -> int:
        mask = 0
        for entry in self._stack:
            mask |= entry
        return mask

    def _newline(self) -> None:
        if self.lines[-1]:
            self.lines.append([])

    # -- HTMLParser hooks ---------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self._newline()
            return
        if tag in _BLOCK_TAGS:
            self._newline()

        mask = _TAG_STYLES.get(tag, 0)
        for name, value in attrs:
            if name == "style" and value:
                mask |= _mask_from_style_attribute(value)
        if mask:
            self.saw_styling = True
        self._stack.append(mask)

    def handle_endtag(self, tag: str) -> None:
        if tag == "br":
            return
        if self._stack:
            self._stack.pop()
        if tag in _BLOCK_TAGS:
            self._newline()

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag == "br":
            self._newline()

    def handle_data(self, data: str) -> None:
        if not data:
            return
        # A newline inside the markup is layout, not content; contenteditable
        # signals real breaks with <br> and block tags.
        text = data.replace("\r", "").replace("\n", " ")
        if not text.strip() and not self.lines[-1]:
            return
        self.lines[-1].append(StyledRun(mask=self._mask, text=text))


def _dominant_mask(runs: list[StyledRun]) -> int:
    """The style that covers most of a line's visible text.

    Formatting a single word inside a turn should not hand that word to another
    speaker, so the line as a whole takes the style that dominates it.
    """
    weights: dict[int, int] = {}
    for run in runs:
        length = len(run.text.strip())
        if length:
            weights[run.mask] = weights.get(run.mask, 0) + length
    if not weights:
        return 0
    # Ties resolve to the earliest slot, keeping the choice deterministic.
    best = max(weights.values())
    return min(
        (mask for mask, weight in weights.items() if weight == best),
        key=slot_index,
    )


@dataclass(frozen=True)
class StyledLine:
    mask: int
    text: str


def extract_styled_lines(html: str) -> tuple[list[StyledLine], bool]:
    """Return the document's lines with their style, and whether any was styled."""
    parser = _StyledLineExtractor()
    parser.feed(html)
    parser.close()

    lines: list[StyledLine] = []
    for runs in parser.lines:
        text = "".join(run.text for run in runs).strip()
        if not text:
            continue
        lines.append(StyledLine(mask=_dominant_mask(runs), text=text))
    return lines, parser.saw_styling


def looks_styled(source: str) -> bool:
    """Whether the source carries speaker styling worth parsing."""
    if "<" not in source:
        return False
    _, saw_styling = extract_styled_lines(source)
    return saw_styling


def html_to_plain_text(html: str) -> str:
    """Strip markup, keeping line structure."""
    lines, _ = extract_styled_lines(html)
    return "\n".join(line.text for line in lines)
