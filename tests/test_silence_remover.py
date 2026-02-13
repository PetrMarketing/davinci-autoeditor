"""Тесты для core/silence_remover.py — автоопределение порога тишины."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import patch, MagicMock

from core.silence_remover import auto_detect_threshold


class TestAutoDetectThreshold(unittest.TestCase):
    @patch("core.silence_remover.os.path.isfile", return_value=True)
    @patch("core.silence_remover.subprocess.run")
    def test_parses_mean_volume(self, mock_run, _):
        mock_run.return_value = MagicMock(
            stderr="[Parsed_volumedetect_0] mean_volume: -25.3 dB\n"
                   "[Parsed_volumedetect_0] max_volume: -2.1 dB"
        )
        result = auto_detect_threshold("/fake/video.mp4")
        # -25.3 + 3 = -22.3 → rounded = -22
        self.assertEqual(result, -22)

    @patch("core.silence_remover.os.path.isfile", return_value=True)
    @patch("core.silence_remover.subprocess.run")
    def test_quiet_audio(self, mock_run, _):
        mock_run.return_value = MagicMock(
            stderr="mean_volume: -45.7 dB"
        )
        result = auto_detect_threshold("/fake/video.mp4")
        # -45.7 + 3 = -42.7 → rounded = -43
        self.assertEqual(result, -43)

    @patch("core.silence_remover.os.path.isfile", return_value=True)
    @patch("core.silence_remover.subprocess.run")
    def test_loud_audio(self, mock_run, _):
        mock_run.return_value = MagicMock(
            stderr="mean_volume: -12.0 dB"
        )
        result = auto_detect_threshold("/fake/video.mp4")
        # -12.0 + 3 = -9.0 → -9
        self.assertEqual(result, -9)

    @patch("core.silence_remover.os.path.isfile", return_value=True)
    @patch("core.silence_remover.subprocess.run")
    def test_fallback_when_no_volume(self, mock_run, _):
        mock_run.return_value = MagicMock(
            stderr="some random output without volume info"
        )
        result = auto_detect_threshold("/fake/video.mp4")
        self.assertEqual(result, -40)

    @patch("core.silence_remover.os.path.isfile", return_value=True)
    @patch("core.silence_remover.subprocess.run")
    def test_ffmpeg_command_correct(self, mock_run, _):
        mock_run.return_value = MagicMock(stderr="mean_volume: -30.0 dB")
        auto_detect_threshold("/tmp/test.mp4")
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-af", cmd)
        self.assertIn("volumedetect", cmd[cmd.index("-af") + 1])

    def test_file_not_found_returns_default(self):
        result = auto_detect_threshold("/nonexistent/file.mp4")
        self.assertEqual(result, -40)


if __name__ == "__main__":
    unittest.main()
