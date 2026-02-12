"""Тесты для config.py"""

import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
import config as config_module


class TestConfig(unittest.TestCase):
    def setUp(self):
        # Перенаправляем файл конфига во временную директорию
        self._orig_file = config_module.CONFIG_FILE
        self._tmpdir = tempfile.mkdtemp()
        self._tmp_file = os.path.join(self._tmpdir, "test_config.json")
        config_module.CONFIG_FILE = self._tmp_file
        # Удаляем файл перед каждым тестом для чистого состояния
        if os.path.exists(self._tmp_file):
            os.unlink(self._tmp_file)

    def tearDown(self):
        config_module.CONFIG_FILE = self._orig_file
        if os.path.exists(self._tmp_file):
            os.unlink(self._tmp_file)
        os.rmdir(self._tmpdir)

    def test_defaults(self):
        c = config_module.Config()
        self.assertEqual(c.get("silence_threshold_db"), -40)
        self.assertEqual(c.get("zoom_min"), 1.0)
        self.assertEqual(c.get("openrouter_model"), "google/gemini-2.0-flash-001")

    def test_set_and_get(self):
        c = config_module.Config()
        c.set("main_video_path", "/tmp/video.mp4")
        self.assertEqual(c.get("main_video_path"), "/tmp/video.mp4")

    def test_save_and_load(self):
        c = config_module.Config()
        c.set("openrouter_api_key", "test-key-123")
        c.save()

        c2 = config_module.Config()
        self.assertEqual(c2.get("openrouter_api_key"), "test-key-123")

    def test_step_status(self):
        c = config_module.Config()
        self.assertEqual(c.get_step_status("1_import"), "pending")
        c.set_step_status("1_import", "done")
        self.assertEqual(c.get_step_status("1_import"), "done")

    def test_reset_steps(self):
        c = config_module.Config()
        c.set_step_status("1_import", "done")
        c.set_step_status("2_sync", "error")
        c.reset_steps()
        self.assertEqual(c.get_step_status("1_import"), "pending")
        self.assertEqual(c.get_step_status("2_sync"), "pending")

    def test_working_path(self):
        c = config_module.Config()
        c.set("working_dir", "/tmp/work")
        self.assertEqual(c.working_path("original.srt"), "/tmp/work/original.srt")

    def test_missing_key_default(self):
        c = config_module.Config()
        self.assertIsNone(c.get("nonexistent_key"))
        self.assertEqual(c.get("nonexistent_key", "fallback"), "fallback")

    def test_persistence_survives_reload(self):
        c = config_module.Config()
        c.set("zoom_max", 1.5)
        c.set_step_status("3_silence", "running")
        c.save()

        c2 = config_module.Config()
        self.assertEqual(c2.get("zoom_max"), 1.5)
        self.assertEqual(c2.get_step_status("3_silence"), "running")
        # Умолчания должны быть сохранены
        self.assertEqual(c2.get("silence_threshold_db"), -40)


if __name__ == "__main__":
    unittest.main()
