from __future__ import annotations

import pytest

from app.domain.parsing import (
    parse_dialogue,
    parse_monologue,
    parse_script,
    speaker_labels,
    split_sentences,
)


class TestSplitSentences:
    def test_splits_on_terminal_punctuation(self):
        assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]

    def test_empty_input(self):
        assert split_sentences("   ") == []

    @pytest.mark.parametrize(
        "text",
        [
            "Mr. Smith arrived early.",
            "Dr. Chen and Prof. Ito met.",
            "The U.S. economy grew.",
            "Use a tokenizer, e.g. one that handles this.",
            "It rose by 3.5 percent last year.",
            "J. R. R. Tolkien wrote it.",
        ],
    )
    def test_abbreviations_and_decimals_stay_in_one_sentence(self, text):
        assert split_sentences(text) == [text]

    def test_abbreviation_followed_by_real_sentence_break(self):
        assert split_sentences("Mr. Smith arrived. He was late.") == [
            "Mr. Smith arrived.",
            "He was late.",
        ]

    def test_quoted_sentence(self):
        assert split_sentences('"Stop." She turned away.') == [
            '"Stop."',
            "She turned away.",
        ]

    def test_text_without_terminal_punctuation(self):
        assert split_sentences("no final period") == ["no final period"]


class TestParseMonologue:
    def test_orders_segments_and_drops_speaker(self):
        segments = parse_monologue("First one. Second one.")
        assert [s.order_index for s in segments] == [0, 1]
        assert [s.text for s in segments] == ["First one.", "Second one."]
        assert all(s.speaker_label is None for s in segments)

    def test_marks_paragraph_starts(self):
        segments = parse_monologue("A one. A two.\n\nB one.")
        assert [s.starts_paragraph for s in segments] == [False, False, True]


class TestParseDialogue:
    def test_bracket_form(self):
        segments = parse_dialogue("[A]\nHello.\n\n[B]\nHi.")
        assert [(s.speaker_label, s.text) for s in segments] == [
            ("A", "Hello."),
            ("B", "Hi."),
        ]

    def test_inline_form(self):
        segments = parse_dialogue("A: Hello.\nB: Hi.")
        assert [(s.speaker_label, s.text) for s in segments] == [
            ("A", "Hello."),
            ("B", "Hi."),
        ]

    def test_multi_sentence_turn_splits_but_keeps_speaker(self):
        segments = parse_dialogue("[A]\nHello. How are you?")
        assert [(s.speaker_label, s.text) for s in segments] == [
            ("A", "Hello."),
            ("A", "How are you?"),
        ]

    def test_multi_line_turn_is_joined(self):
        segments = parse_dialogue("[A]\nHello\nthere.")
        assert [s.text for s in segments] == ["Hello there."]

    def test_prose_containing_a_colon_is_not_a_speaker(self):
        segments = parse_dialogue(
            "[A]\nThere is one rule: never guess.",
        )
        assert [(s.speaker_label, s.text) for s in segments] == [
            ("A", "There is one rule: never guess.")
        ]

    def test_speaker_labels_in_first_appearance_order(self):
        segments = parse_dialogue("[B]\nOne.\n\n[A]\nTwo.\n\n[B]\nThree.")
        assert speaker_labels(segments) == ["B", "A"]

    def test_order_index_is_contiguous(self):
        segments = parse_dialogue("[A]\nOne. Two.\n\n[B]\nThree.")
        assert [s.order_index for s in segments] == [0, 1, 2]


class TestParseScript:
    def test_dialogue_without_markup_falls_back_to_monologue(self):
        segments = parse_script("Just prose. No speakers.", mode="dialogue")
        assert len(segments) == 2
        assert all(s.speaker_label is None for s in segments)

    def test_monologue_mode_ignores_speaker_markup(self):
        segments = parse_script("[A]\nHello.", mode="monologue")
        assert all(s.speaker_label is None for s in segments)


class TestInlineSpeakerShape:
    """The inline `A: text` form must not swallow ordinary prose."""

    @pytest.mark.parametrize(
        "line,label",
        [
            ("A: Hello.", "A"),
            ("Anna: Hello.", "Anna"),
            ("Speaker A: Hello.", "Speaker A"),
            ("Person 1: Hello.", "Person 1"),
        ],
    )
    def test_name_shaped_labels_are_speakers(self, line, label):
        segments = parse_dialogue(line)
        assert segments[0].speaker_label == label

    @pytest.mark.parametrize(
        "line",
        [
            "There is one rule: never guess.",
            "In summary: the trend continued.",
            "she said: hello.",
        ],
    )
    def test_prose_with_a_colon_is_not_a_speaker(self, line):
        segments = parse_dialogue(f"[A]\n{line}")
        assert segments[0].speaker_label == "A"
        assert segments[0].text == line
