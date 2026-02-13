"""Тесты для core/audio_sync.py"""

import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import patch, MagicMock

from core.audio_sync import _detect_first_sound, auto_sync_audio
import config as config_module


class FakeClip:
    """Мок для MediaPoolItem."""
    def __init__(self, name, path=""):
        self._name = name
        self._path = path

    def GetName(self):
        return self._name

    def GetClipProperty(self, prop):
        if prop == "File Path":
            return self._path
        return ""


class TestDetectFirstSound(unittest.TestCase):
    @patch("core.audio_sync.subprocess.run")
    def test_parses_silence_end(self, mock_run):
        mock_run.return_value = MagicMock(
            stderr="[silencedetect @ 0x1234] silence_end: 2.456 | silence_duration: 2.456"
        )
        result = _detect_first_sound("/fake/path.mp4")
        self.assertAlmostEqual(result, 2.456)

    @patch("core.audio_sync.subprocess.run")
    def test_returns_zero_when_no_silence(self, mock_run):
        mock_run.return_value = MagicMock(stderr="no silence detected here")
        result = _detect_first_sound("/fake/path.mp4")
        self.assertEqual(result, 0.0)

    @patch("core.audio_sync.subprocess.run")
    def test_custom_threshold(self, mock_run):
        mock_run.return_value = MagicMock(stderr="silence_end: 1.0")
        _detect_first_sound("/fake/path.mp4", threshold_db=-50)
        cmd = mock_run.call_args[0][0]
        self.assertIn("silencedetect=n=-50dB:d=0.1", cmd[cmd.index("-af") + 1])

    @patch("core.audio_sync.subprocess.run")
    def test_multiple_silence_ends_takes_first(self, mock_run):
        mock_run.return_value = MagicMock(
            stderr="silence_end: 0.500\nsilence_end: 3.200\nsilence_end: 7.800"
        )
        result = _detect_first_sound("/fake/path.mp4")
        self.assertAlmostEqual(result, 0.5)


class TestAutoSyncAudio(unittest.TestCase):
    def setUp(self):
        self._orig_file = config_module.CONFIG_FILE
        self._tmpdir = tempfile.mkdtemp()
        self._tmp_file = os.path.join(self._tmpdir, "test_config.json")
        config_module.CONFIG_FILE = self._tmp_file

    def tearDown(self):
        config_module.CONFIG_FILE = self._orig_file
        for f in os.listdir(self._tmpdir):
            os.unlink(os.path.join(self._tmpdir, f))
        os.rmdir(self._tmpdir)

    def test_no_main_clip_raises(self):
        with self.assertRaises(RuntimeError):
            auto_sync_audio({"main": None, "screencast": FakeClip("sc")})

    def test_no_screencast_returns_zero(self):
        result = auto_sync_audio({"main": FakeClip("main"), "screencast": None})
        self.assertEqual(result, 0)

    def test_no_file_paths_returns_zero(self):
        result = auto_sync_audio({
            "main": FakeClip("main", ""),
            "screencast": FakeClip("sc", ""),
        })
        self.assertEqual(result, 0)

    @patch("core.audio_sync._detect_first_sound")
    @patch("core.audio_sync.subprocess.run")
    def test_calculates_offset(self, mock_run, mock_detect):
        # Основной клип: первый звук на 1.0с, скринкаст: на 3.5с → смещение 2500мс
        mock_detect.side_effect = [1.0, 3.5]
        mock_run.return_value = MagicMock()  # для loudnorm

        result = auto_sync_audio({
            "main": FakeClip("main", "/tmp/main.mp4"),
            "screencast": FakeClip("sc", "/tmp/sc.mp4"),
        })
        self.assertEqual(result, 2500)

    @patch("core.audio_sync._detect_first_sound")
    @patch("core.audio_sync.subprocess.run")
    def test_small_offset_zeroed(self, mock_run, mock_detect):
        # Смещение < 50мс обнуляется
        mock_detect.side_effect = [1.000, 1.030]
        mock_run.return_value = MagicMock()

        result = auto_sync_audio({
            "main": FakeClip("main", "/tmp/main.mp4"),
            "screencast": FakeClip("sc", "/tmp/sc.mp4"),
        })
        self.assertEqual(result, 0)

    @patch("core.audio_sync._detect_first_sound")
    @patch("core.audio_sync.subprocess.run")
    def test_saves_to_config(self, mock_run, mock_detect):
        mock_detect.side_effect = [0.5, 2.5]
        mock_run.return_value = MagicMock()

        cfg = config_module.Config()
        cfg.set("working_dir", "")  # без рабочей директории

        auto_sync_audio({
            "main": FakeClip("main", "/tmp/main.mp4"),
            "screencast": FakeClip("sc", "/tmp/sc.mp4"),
        }, config=cfg)

        self.assertEqual(cfg.get("audio_offset_ms"), 2000)

    @patch("core.audio_sync._detect_first_sound")
    @patch("core.audio_sync.subprocess.run")
    def test_saves_json_to_working_dir(self, mock_run, mock_detect):
        mock_detect.side_effect = [1.0, 3.0]
        mock_run.return_value = MagicMock()

        cfg = config_module.Config()
        cfg.set("working_dir", self._tmpdir)

        auto_sync_audio({
            "main": FakeClip("main", "/tmp/main.mp4"),
            "screencast": FakeClip("sc", "/tmp/sc.mp4"),
        }, config=cfg)

        json_path = os.path.join(self._tmpdir, "audio_sync.json")
        self.assertTrue(os.path.exists(json_path))

        with open(json_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["offset_ms"], 2000)
        self.assertAlmostEqual(data["offset_sec"], 2.0)
        self.assertAlmostEqual(data["main_onset_sec"], 1.0)
        self.assertAlmostEqual(data["screencast_onset_sec"], 3.0)

    @patch("core.audio_sync._detect_first_sound")
    @patch("core.audio_sync.subprocess.run")
    def test_negative_offset(self, mock_run, mock_detect):
        # Скринкаст начинается раньше основного → отрицательное смещение
        mock_detect.side_effect = [5.0, 2.0]
        mock_run.return_value = MagicMock()

        result = auto_sync_audio({
            "main": FakeClip("main", "/tmp/main.mp4"),
            "screencast": FakeClip("sc", "/tmp/sc.mp4"),
        })
        self.assertEqual(result, -3000)


if __name__ == "__main__":
    unittest.main()
