"""Speakers marked by bold / italic / underline instead of [A] / [B]."""

from __future__ import annotations

import pytest

from app.domain.parsing import parse_script, parse_styled_dialogue
from app.domain.styled_parsing import (
    BOLD,
    ITALIC,
    MAX_STYLE_SPEAKERS,
    UNDERLINE,
    extract_styled_lines,
    html_to_plain_text,
    looks_styled,
    mask_for_label,
    speaker_label_for_mask,
)


class TestSlotMapping:
    def test_eight_combinations_exactly(self):
        # Three independent marks, so eight speakers -- no more, no fewer.
        assert MAX_STYLE_SPEAKERS == 8

    @pytest.mark.parametrize(
        "mask,label",
        [
            (0, "A"),
            (BOLD, "B"),
            (ITALIC, "C"),
            (UNDERLINE, "D"),
            (BOLD | ITALIC, "E"),
            (BOLD | UNDERLINE, "F"),
            (ITALIC | UNDERLINE, "G"),
            (BOLD | ITALIC | UNDERLINE, "H"),
        ],
    )
    def test_each_style_has_a_fixed_slot(self, mask, label):
        # The mapping must not shift as a script is edited: bold is always
        # Voice 2, whatever else the document contains.
        assert speaker_label_for_mask(mask) == label
        assert mask_for_label(label) == mask

    def test_label_beyond_the_range_has_no_style(self):
        assert mask_for_label("Z") is None


class TestExtraction:
    def test_plain_text_is_one_unstyled_line(self):
        lines, styled = extract_styled_lines("Just text.")
        assert [(line.mask, line.text) for line in lines] == [(0, "Just text.")]
        assert styled is False

    def test_tags_and_inline_styles_are_both_understood(self):
        # Browsers disagree: some emit <b>, others a span with font-weight.
        for html in (
            "<b>Bold.</b>",
            "<strong>Bold.</strong>",
            '<span style="font-weight: bold">Bold.</span>',
            '<span style="font-weight:700">Bold.</span>',
        ):
            lines, styled = extract_styled_lines(html)
            assert lines[0].mask == BOLD, html
            assert styled is True

    def test_italic_and_underline_variants(self):
        assert extract_styled_lines("<i>x</i>")[0][0].mask == ITALIC
        assert extract_styled_lines("<em>x</em>")[0][0].mask == ITALIC
        assert extract_styled_lines('<span style="font-style:italic">x</span>')[0][0].mask == ITALIC
        assert extract_styled_lines("<u>x</u>")[0][0].mask == UNDERLINE
        assert (
            extract_styled_lines('<span style="text-decoration:underline">x</span>')[0][0].mask
            == UNDERLINE
        )

    def test_nested_styles_combine(self):
        lines, _ = extract_styled_lines("<b><i><u>All three.</u></i></b>")
        assert lines[0].mask == BOLD | ITALIC | UNDERLINE

    def test_div_and_br_separate_lines(self):
        lines, _ = extract_styled_lines("One.<div>Two.</div>Three.<br>Four.")
        assert [line.text for line in lines] == ["One.", "Two.", "Three.", "Four."]

    def test_blank_lines_are_dropped(self):
        lines, _ = extract_styled_lines("<div>One.</div><div><br></div><div>Two.</div>")
        assert [line.text for line in lines] == ["One.", "Two."]

    def test_entities_are_decoded(self):
        lines, _ = extract_styled_lines("<div>Tom &amp; Jerry said &quot;hi&quot;.</div>")
        assert lines[0].text == 'Tom & Jerry said "hi".'

    def test_a_single_styled_word_does_not_hijack_the_line(self):
        # Emphasising one word inside a turn must not hand it to another
        # speaker; the line takes the style that dominates it.
        lines, _ = extract_styled_lines(
            "<div>This is a fairly long plain sentence with one <b>word</b> bold.</div>"
        )
        assert len(lines) == 1
        assert lines[0].mask == 0

    def test_a_mostly_bold_line_is_bold(self):
        lines, _ = extract_styled_lines(
            "<div><b>Nearly all of this line is bold</b> except.</div>"
        )
        assert lines[0].mask == BOLD

    def test_html_to_plain_text_keeps_line_structure(self):
        assert html_to_plain_text("<div>One.</div><div><b>Two.</b></div>") == "One.\nTwo."


class TestLooksStyled:
    def test_detects_styling(self):
        assert looks_styled("<div><b>Bold.</b></div>") is True

    def test_plain_html_is_not_styled(self):
        assert looks_styled("<div>Plain.</div>") is False

    def test_text_without_markup_is_not_styled(self):
        assert looks_styled("[A]\nHello.") is False


class TestParseStyledDialogue:
    def test_each_style_becomes_its_own_speaker(self):
        html = (
            "<div>Plain line.</div>"
            "<div><b>Bold line.</b></div>"
            "<div><i>Italic line.</i></div>"
            "<div><u>Underline line.</u></div>"
        )
        segments = parse_styled_dialogue(html)
        assert [(s.speaker_label, s.text) for s in segments] == [
            ("A", "Plain line."),
            ("B", "Bold line."),
            ("C", "Italic line."),
            ("D", "Underline line."),
        ]

    def test_all_eight_combinations_are_addressable(self):
        html = "".join(
            f"<div>{open_}Line {i}.{close}</div>"
            for i, (open_, close) in enumerate(
                [
                    ("", ""),
                    ("<b>", "</b>"),
                    ("<i>", "</i>"),
                    ("<u>", "</u>"),
                    ("<b><i>", "</i></b>"),
                    ("<b><u>", "</u></b>"),
                    ("<i><u>", "</u></i>"),
                    ("<b><i><u>", "</u></i></b>"),
                ]
            )
        )
        segments = parse_styled_dialogue(html)
        assert [s.speaker_label for s in segments] == list("ABCDEFGH")

    def test_a_turn_splits_into_sentences_but_keeps_its_speaker(self):
        segments = parse_styled_dialogue("<div><b>One. Two.</b></div>")
        assert [(s.speaker_label, s.text) for s in segments] == [
            ("B", "One."),
            ("B", "Two."),
        ]

    def test_abbreviations_still_survive(self):
        segments = parse_styled_dialogue(
            "<div><i>Dr. Chen asked for it by 3.30 p.m.</i></div>"
        )
        assert [s.text for s in segments] == ["Dr. Chen asked for it by 3.30 p.m."]

    def test_order_index_is_contiguous(self):
        segments = parse_styled_dialogue(
            "<div>One. Two.</div><div><b>Three.</b></div>"
        )
        assert [s.order_index for s in segments] == [0, 1, 2]


class TestParseScriptDispatch:
    def test_styling_wins_over_bracket_markers(self):
        # A styled document may contain square brackets as ordinary
        # punctuation, so styling must take precedence.
        html = "<div>See [note 1] here.</div><div><b>Bold reply.</b></div>"
        segments = parse_script(html, "dialogue")
        assert [s.speaker_label for s in segments] == ["A", "B"]
        assert "[note 1]" in segments[0].text

    def test_markers_still_work_when_nothing_is_styled(self):
        segments = parse_script("[A]\nHello.\n\n[B]\nHi.", "dialogue")
        assert [(s.speaker_label, s.text) for s in segments] == [
            ("A", "Hello."),
            ("B", "Hi."),
        ]

    def test_unstyled_html_falls_back_to_marker_parsing(self):
        segments = parse_script("<div>[A]</div><div>Hello.</div>", "dialogue")
        assert segments[0].speaker_label == "A"

    def test_monologue_strips_markup(self):
        segments = parse_script("<div><b>One.</b></div><div>Two.</div>", "monologue")
        assert [s.text for s in segments] == ["One.", "Two."]
        assert all(s.speaker_label is None for s in segments)


class TestUnmarkedDialogue:
    """A dialogue with no styling and no markers is a dialogue of one.

    Leaving the speaker unset would give the project no voice slot, and so no
    way to pick a voice at all.
    """

    def test_plain_dialogue_gets_one_speaker(self):
        segments = parse_script("One sentence. Two sentences.", "dialogue")
        assert {s.speaker_label for s in segments} == {"A"}

    def test_plain_html_dialogue_gets_one_speaker(self):
        segments = parse_script("<div>One.</div><div>Two.</div>", "dialogue")
        assert {s.speaker_label for s in segments} == {"A"}

    def test_removing_all_styling_leaves_exactly_one_speaker(self):
        styled = "<div>Plain.</div><div><b>Bold.</b></div>"
        assert {s.speaker_label for s in parse_script(styled, "dialogue")} == {"A", "B"}

        unstyled = "<div>Plain.</div><div>Bold.</div>"
        assert {s.speaker_label for s in parse_script(unstyled, "dialogue")} == {"A"}

    def test_monologue_mode_still_has_no_speaker(self):
        segments = parse_script("One sentence.", "monologue")
        assert all(s.speaker_label is None for s in segments)
