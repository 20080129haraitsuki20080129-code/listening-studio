"""Transcript PDF rendering.

Kept in infrastructure because it is a concrete document-format concern; the
render service hands it plain data.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.domain.errors import AudioProcessingFailed

# Titles can be Japanese while the script itself is English. This CID font
# ships with reportlab, so no font file has to be installed alongside it.
_CJK_FONT = "HeiseiKakuGo-W5"
_cjk_registered = False


def _ensure_cjk_font() -> str:
    global _cjk_registered
    if not _cjk_registered:
        pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT))
        _cjk_registered = True
    return _CJK_FONT


@dataclass(frozen=True)
class TranscriptLine:
    index: int
    speaker: str | None
    text: str
    duration_ms: int | None


def _escape(text: str) -> str:
    """Platypus reads a mini-HTML dialect, so markup characters must be escaped."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return ""
    seconds = duration_ms / 1000
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def build_transcript_pdf(
    *,
    title: str,
    mode: str,
    lines: list[TranscriptLine],
    total_duration_ms: int | None = None,
    word_count: int | None = None,
) -> bytes:
    cjk = _ensure_cjk_font()
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TranscriptTitle",
        parent=styles["Title"],
        fontName=cjk,
        fontSize=18,
        leading=24,
        alignment=TA_LEFT,
        spaceAfter=2 * mm,
    )
    meta_style = ParagraphStyle(
        "TranscriptMeta",
        parent=styles["Normal"],
        fontName=cjk,
        fontSize=9,
        textColor="#666666",
        spaceAfter=6 * mm,
    )
    speaker_style = ParagraphStyle(
        "TranscriptSpeaker",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor="#444444",
        spaceAfter=1,
    )
    body_style = ParagraphStyle(
        "TranscriptBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=17,
        spaceAfter=4 * mm,
    )

    story = [Paragraph(_escape(title), title_style)]

    meta_parts = [mode]
    if word_count:
        meta_parts.append(f"{word_count} words")
    if total_duration_ms:
        meta_parts.append(_format_duration(total_duration_ms))
    story.append(Paragraph(_escape(" · ".join(meta_parts)), meta_style))

    for line in lines:
        header_bits = [f"{line.index}."]
        if line.speaker:
            header_bits.append(line.speaker)
        duration = _format_duration(line.duration_ms)
        if duration:
            header_bits.append(f"({duration})")
        block = [
            Paragraph(_escape(" ".join(header_bits)), speaker_style),
            Paragraph(_escape(line.text), body_style),
        ]
        # Keep a number with its sentence when the page breaks.
        story.append(KeepTogether(block))

    if not lines:
        story.append(Spacer(1, 4 * mm))

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
    )
    try:
        document.build(story)
    except Exception as exc:  # re-raised as a normalized error
        raise AudioProcessingFailed(
            f"Could not build the transcript PDF: {exc}"
        ) from exc
    return buffer.getvalue()
