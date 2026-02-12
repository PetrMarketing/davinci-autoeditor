"""Тесты для core/ai_processor.py — только оффлайн-логика (без API-вызовов)."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

try:
    from core.ai_processor import build_srt_chunk_text
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@unittest.skipUnless(HAS_HTTPX, "httpx не установлен — пропуск тестов ai_processor")
class TestBuildSrtChunkText(unittest.TestCase):
    def test_basic(self):
        from utils.srt_parser import SubtitleBlock
        blocks = [
            SubtitleBlock(1, 1000, 3000, "Привет", False),
            SubtitleBlock(2, 4000, 6000, "Мир", False),
        ]
        text = build_srt_chunk_text(blocks)
        self.assertIn("1\n00:00:01,000 --> 00:00:03,000\nПривет", text)
        self.assertIn("2\n00:00:04,000 --> 00:00:06,000\nМир", text)

    def test_empty(self):
        text = build_srt_chunk_text([])
        self.assertEqual(text, "")

    def test_preserves_timecodes(self):
        from utils.srt_parser import SubtitleBlock
        blocks = [SubtitleBlock(5, 65123, 70456, "Тест", False)]
        text = build_srt_chunk_text(blocks)
        self.assertIn("00:01:05,123", text)
        self.assertIn("00:01:10,456", text)


if __name__ == "__main__":
    unittest.main()
