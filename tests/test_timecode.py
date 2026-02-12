"""Тесты для utils/timecode.py"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.timecode import (
    ms_to_timecode, timecode_to_ms,
    ms_to_frames, frames_to_ms,
    frames_to_resolve_tc, resolve_tc_to_frames,
)
import unittest


class TestMsToTimecode(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(ms_to_timecode(0), "00:00:00,000")

    def test_simple(self):
        self.assertEqual(ms_to_timecode(1500), "00:00:01,500")

    def test_minutes(self):
        self.assertEqual(ms_to_timecode(65000), "00:01:05,000")

    def test_hours(self):
        self.assertEqual(ms_to_timecode(3661234), "01:01:01,234")

    def test_negative_clamped(self):
        self.assertEqual(ms_to_timecode(-100), "00:00:00,000")


class TestTimecodeToMs(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(timecode_to_ms("00:00:00,000"), 0)

    def test_with_comma(self):
        self.assertEqual(timecode_to_ms("00:00:01,500"), 1500)

    def test_with_dot(self):
        self.assertEqual(timecode_to_ms("00:00:01.500"), 1500)

    def test_hours(self):
        self.assertEqual(timecode_to_ms("01:01:01,234"), 3661234)

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            timecode_to_ms("invalid")

    def test_roundtrip(self):
        for ms in [0, 500, 1234, 65000, 3661234, 7200000]:
            tc = ms_to_timecode(ms)
            self.assertEqual(timecode_to_ms(tc), ms)


class TestFrameConversions(unittest.TestCase):
    def test_ms_to_frames_25fps(self):
        self.assertEqual(ms_to_frames(1000, 25.0), 25)
        self.assertEqual(ms_to_frames(0, 25.0), 0)
        self.assertEqual(ms_to_frames(40, 25.0), 1)

    def test_frames_to_ms_25fps(self):
        self.assertEqual(frames_to_ms(25, 25.0), 1000)
        self.assertEqual(frames_to_ms(0, 25.0), 0)
        self.assertEqual(frames_to_ms(1, 25.0), 40)

    def test_roundtrip(self):
        for frames in [0, 1, 25, 100, 750, 1500]:
            ms = frames_to_ms(frames, 25.0)
            self.assertEqual(ms_to_frames(ms, 25.0), frames)


class TestResolveTimecode(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(frames_to_resolve_tc(0, 25.0), "00:00:00:00")

    def test_one_second(self):
        self.assertEqual(frames_to_resolve_tc(25, 25.0), "00:00:01:00")

    def test_with_frames(self):
        self.assertEqual(frames_to_resolve_tc(27, 25.0), "00:00:01:02")

    def test_complex(self):
        # 1h 1m 1s 12f = (3661 * 25) + 12 = 91537
        self.assertEqual(frames_to_resolve_tc(91537, 25.0), "01:01:01:12")

    def test_parse(self):
        self.assertEqual(resolve_tc_to_frames("00:00:00:00", 25.0), 0)
        self.assertEqual(resolve_tc_to_frames("00:00:01:00", 25.0), 25)
        self.assertEqual(resolve_tc_to_frames("01:01:01:12", 25.0), 91537)

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            resolve_tc_to_frames("00:00:00", 25.0)

    def test_roundtrip(self):
        for frames in [0, 1, 25, 100, 750, 91537]:
            tc = frames_to_resolve_tc(frames, 25.0)
            self.assertEqual(resolve_tc_to_frames(tc, 25.0), frames)


if __name__ == "__main__":
    unittest.main()
