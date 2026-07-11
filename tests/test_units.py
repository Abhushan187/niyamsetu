# backend/tests/test_units.py
# ─────────────────────────────────────────────────────────
# Unit tests for core/language.py — pure functions only.
# No MongoDB, no Ollama, no FAISS needed — safe to run in CI.
# ─────────────────────────────────────────────────────────

import sys
import os
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.language import (
    detect_language,
    clean_text,
    truncate_for_context,
    format_chat_history,
)


class TestDetectLanguage(unittest.TestCase):

    def test_pure_english(self):
        self.assertEqual(detect_language("What is this GR about?"), "english")

    def test_pure_marathi(self):
        self.assertEqual(detect_language("या निर्णयाचा विषय काय आहे?"), "marathi")

    def test_mixed_text_with_marathi_over_threshold(self):
        # Mixed sentence with enough Devanagari characters to cross 15%
        self.assertEqual(detect_language("या GR मध्ये काय आहे विषय?"), "marathi")

    def test_empty_string_defaults_english(self):
        self.assertEqual(detect_language(""), "english")

    def test_whitespace_only_defaults_english(self):
        self.assertEqual(detect_language("     "), "english")

    def test_none_like_input_defaults_english(self):
        # detect_language guards against falsy input
        self.assertEqual(detect_language(None), "english")

    def test_numbers_and_punctuation_only(self):
        # No Devanagari at all — should stay English regardless of content
        self.assertEqual(detect_language("12345 !@#$%"), "english")


class TestCleanText(unittest.TestCase):

    def test_collapses_multiple_spaces(self):
        self.assertEqual(clean_text("Hello    World"), "Hello World")

    def test_collapses_excessive_newlines(self):
        result = clean_text("Para one\n\n\n\nPara two")
        self.assertEqual(result, "Para one\n\nPara two")

    def test_strips_leading_trailing_whitespace(self):
        self.assertEqual(clean_text("   Hello World   "), "Hello World")

    def test_empty_string_returns_empty(self):
        self.assertEqual(clean_text(""), "")

    def test_none_returns_empty_string(self):
        self.assertEqual(clean_text(None), "")


class TestTruncateForContext(unittest.TestCase):

    def test_short_text_unchanged(self):
        text = "This is a short GR summary."
        self.assertEqual(truncate_for_context(text, max_chars=100), text)

    def test_truncates_at_sentence_boundary(self):
        # Build text where a '.' sits comfortably within the last 20% window
        text = "First sentence. " * 50   # long, punctuated repeatedly
        result = truncate_for_context(text, max_chars=200)
        self.assertLessEqual(len(result), 200)
        # Should end on a sentence boundary, not mid-word
        self.assertTrue(result.endswith('.'))

    def test_truncates_devanagari_full_stop(self):
        text = "मजकूर एक।" * 100
        result = truncate_for_context(text, max_chars=200)
        self.assertLessEqual(len(result), 200)

    def test_falls_back_to_hard_cut_when_no_boundary_nearby(self):
        # No punctuation at all — must hard-cut at max_chars
        text = "a" * 5000
        result = truncate_for_context(text, max_chars=1000)
        self.assertEqual(len(result), 1000)


class TestFormatChatHistory(unittest.TestCase):

    def test_empty_history_returns_empty_string(self):
        self.assertEqual(format_chat_history([]), "")

    def test_none_history_returns_empty_string(self):
        self.assertEqual(format_chat_history(None), "")

    def test_formats_single_turn(self):
        history = [
            {"role": "user", "content": "What is this GR about?"},
            {"role": "assistant", "content": "This GR concerns transfer policy."},
        ]
        result = format_chat_history(history)
        self.assertIn("User: What is this GR about?", result)
        self.assertIn("Assistant: This GR concerns transfer policy.", result)

    def test_respects_context_window_limit(self):
        # 10 turns (20 messages), window of 2 turns should keep only last 4 messages
        history = []
        for i in range(10):
            history.append({"role": "user", "content": f"Question {i}"})
            history.append({"role": "assistant", "content": f"Answer {i}"})

        result = format_chat_history(history, context_window=2)
        # Should only contain the last 2 turns (Question 8/9, Answer 8/9)
        self.assertIn("Question 8", result)
        self.assertIn("Question 9", result)
        self.assertNotIn("Question 0", result)

    def test_truncates_long_assistant_response(self):
        long_answer = "A" * 600
        history = [
            {"role": "user", "content": "Summarize this GR"},
            {"role": "assistant", "content": long_answer},
        ]
        result = format_chat_history(history)
        # Should be cut to 500 chars + "..." per the function's own rule
        self.assertIn("A" * 500 + "...", result)
        self.assertNotIn("A" * 600, result)


if __name__ == "__main__":
    from json_test_runner import run_module_to_json
    import sys as _sys
    success = run_module_to_json(
        module=_sys.modules[__name__],
        output_path="unit_test_results.json",
        suite_name="Unit Tests (core/language.py)",
    )
    _sys.exit(0 if success else 1)