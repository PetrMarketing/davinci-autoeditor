"""Тесты для utils/srt_parser.py"""

import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from utils.srt_parser import (
    parse_srt, SubtitleBlock, write_srt, read_srt,
    get_keep_segments, merge_silence_and_ai, invert_regions, chunk_blocks,
)


SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,000
Привет, мир!

2
00:00:04,000 --> 00:00:06,000
Это тестовое видео.

3
00:00:07,000 --> 00:00:09,000
[DELETE] Ээээ, ну вот.

4
00:00:10,000 --> 00:00:12,000
Спасибо за просмотр!
"""


class TestParseSrt(unittest.TestCase):
    def test_parse_count(self):
        blocks = parse_srt(SAMPLE_SRT)
        self.assertEqual(len(blocks), 4)

    def test_parse_fields(self):
        blocks = parse_srt(SAMPLE_SRT)
        b = blocks[0]
        self.assertEqual(b.index, 1)
        self.assertEqual(b.start_ms, 1000)
        self.assertEqual(b.end_ms, 3000)
        self.assertEqual(b.text, "Привет, мир!")
        self.assertFalse(b.deleted)

    def test_parse_deleted(self):
        blocks = parse_srt(SAMPLE_SRT)
        b = blocks[2]
        self.assertTrue(b.deleted)
        self.assertEqual(b.text, "Ээээ, ну вот.")

    def test_parse_not_deleted(self):
        blocks = parse_srt(SAMPLE_SRT)
        self.assertFalse(blocks[0].deleted)
        self.assertFalse(blocks[1].deleted)
        self.assertFalse(blocks[3].deleted)

    def test_parse_empty(self):
        blocks = parse_srt("")
        self.assertEqual(len(blocks), 0)

    def test_parse_malformed(self):
        blocks = parse_srt("not valid srt\nblah blah")
        self.assertEqual(len(blocks), 0)


class TestWriteReadSrt(unittest.TestCase):
    def test_write_and_read(self):
        blocks = [
            SubtitleBlock(1, 1000, 3000, "Первая строка", False),
            SubtitleBlock(2, 4000, 6000, "Удалённая", True),
            SubtitleBlock(3, 7000, 9000, "Третья строка", False),
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False) as f:
            path = f.name
        try:
            write_srt(blocks, path)
            loaded = read_srt(path)
            self.assertEqual(len(loaded), 3)
            self.assertEqual(loaded[0].text, "Первая строка")
            self.assertFalse(loaded[0].deleted)
            self.assertTrue(loaded[1].deleted)
            self.assertEqual(loaded[1].text, "Удалённая")
            self.assertEqual(loaded[2].start_ms, 7000)
        finally:
            os.unlink(path)


class TestGetKeepSegments(unittest.TestCase):
    def test_basic(self):
        blocks = parse_srt(SAMPLE_SRT)
        segments = get_keep_segments(blocks)
        # Blocks 0,1 are close (gap 1s > 200ms) so separate; block 2 deleted; block 3 kept
        self.assertTrue(len(segments) >= 2)

    def test_all_deleted(self):
        blocks = [SubtitleBlock(1, 0, 1000, "x", True)]
        segments = get_keep_segments(blocks)
        self.assertEqual(segments, [])

    def test_merge_adjacent(self):
        blocks = [
            SubtitleBlock(1, 0, 1000, "a", False),
            SubtitleBlock(2, 1100, 2000, "b", False),  # gap 100ms < 200ms → merge
        ]
        segments = get_keep_segments(blocks)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0], (0, 2000))


class TestMergeSilenceAndAi(unittest.TestCase):
    def test_empty(self):
        result = merge_silence_and_ai([], [])
        self.assertEqual(result, [])

    def test_silence_only(self):
        silence = [(0, 500), (1000, 1500)]
        result = merge_silence_and_ai(silence, [])
        self.assertEqual(result, [(0, 500), (1000, 1500)])

    def test_ai_only(self):
        blocks = [
            SubtitleBlock(1, 2000, 3000, "x", True),
            SubtitleBlock(2, 4000, 5000, "y", False),
        ]
        result = merge_silence_and_ai([], blocks)
        self.assertEqual(result, [(2000, 3000)])

    def test_overlap_merge(self):
        silence = [(0, 1500)]
        blocks = [SubtitleBlock(1, 1000, 2000, "x", True)]
        result = merge_silence_and_ai(silence, blocks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], (0, 2000))


class TestInvertRegions(unittest.TestCase):
    def test_no_deletes(self):
        result = invert_regions([], 10000)
        self.assertEqual(result, [(0, 10000)])

    def test_full_delete(self):
        result = invert_regions([(0, 10000)], 10000)
        self.assertEqual(result, [])

    def test_middle_delete(self):
        result = invert_regions([(3000, 7000)], 10000)
        self.assertEqual(result, [(0, 3000), (7000, 10000)])

    def test_start_delete(self):
        result = invert_regions([(0, 5000)], 10000)
        self.assertEqual(result, [(5000, 10000)])

    def test_end_delete(self):
        result = invert_regions([(5000, 10000)], 10000)
        self.assertEqual(result, [(0, 5000)])


class TestChunkBlocks(unittest.TestCase):
    def test_exact(self):
        blocks = [SubtitleBlock(i, 0, 1000, "x", False) for i in range(10)]
        chunks = chunk_blocks(blocks, 5)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0]), 5)
        self.assertEqual(len(chunks[1]), 5)

    def test_remainder(self):
        blocks = [SubtitleBlock(i, 0, 1000, "x", False) for i in range(7)]
        chunks = chunk_blocks(blocks, 3)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(len(chunks[2]), 1)

    def test_single_chunk(self):
        blocks = [SubtitleBlock(i, 0, 1000, "x", False) for i in range(3)]
        chunks = chunk_blocks(blocks, 50)
        self.assertEqual(len(chunks), 1)


if __name__ == "__main__":
    unittest.main()
