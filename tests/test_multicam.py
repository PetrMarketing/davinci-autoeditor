"""Тесты для core/multicam.py — логика распределения мультикамеры."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import patch, MagicMock

from core.multicam import distribute_multicam, auto_switch_intervals
from utils.timecode import ms_to_frames


class TestMulticamDistribute(unittest.TestCase):
    """Тесты для distribute_multicam."""

    def _make_mocks(self):
        """Создать моки для Resolve API."""
        mock_mp = MagicMock()
        mock_mp.AppendToTimeline.return_value = True
        mock_timeline = MagicMock()
        mock_timeline.GetTrackCount.return_value = 2
        mock_clip = MagicMock()
        return mock_mp, mock_timeline, mock_clip

    @patch("core.multicam.get_current_timeline")
    @patch("core.multicam.get_media_pool")
    def test_no_timeline_raises(self, mock_get_mp, mock_get_tl):
        mock_get_tl.return_value = None
        mock_get_mp.return_value = MagicMock()
        with self.assertRaises(RuntimeError):
            distribute_multicam(MagicMock(), [(0, 5000)])

    @patch("core.multicam.get_current_timeline")
    @patch("core.multicam.get_media_pool")
    def test_no_screencast_returns_zero(self, mock_get_mp, mock_get_tl):
        mock_get_tl.return_value = MagicMock()
        mock_get_mp.return_value = MagicMock()
        result = distribute_multicam(None, [(0, 5000)])
        self.assertEqual(result, 0)

    @patch("core.multicam.random.randint")
    @patch("core.multicam.get_current_timeline")
    @patch("core.multicam.get_media_pool")
    def test_places_clips_on_v2(self, mock_get_mp, mock_get_tl, mock_randint):
        mock_mp, mock_timeline, mock_clip = self._make_mocks()
        mock_get_mp.return_value = mock_mp
        mock_get_tl.return_value = mock_timeline

        # Фиксируем интервал: 5 секунд
        mock_randint.return_value = 5

        # Один сегмент 20 секунд → 4 чанка по 5с: off, on, off, on
        result = distribute_multicam(
            mock_clip, [(0, 20000)],
            min_interval_sec=5, max_interval_sec=5, fps=25.0,
        )
        # 2 скринкаст-сегмента (чётные — off, нечётные — on)
        self.assertEqual(result, 2)
        mock_mp.AppendToTimeline.assert_called_once()
        clip_infos = mock_mp.AppendToTimeline.call_args[0][0]
        self.assertEqual(len(clip_infos), 2)

        # Все на V2
        for info in clip_infos:
            self.assertEqual(info["trackIndex"], 2)
            self.assertEqual(info["mediaType"], 1)
            self.assertEqual(info["mediaPoolItem"], mock_clip)

    @patch("core.multicam.random.randint")
    @patch("core.multicam.get_current_timeline")
    @patch("core.multicam.get_media_pool")
    def test_audio_offset_applied(self, mock_get_mp, mock_get_tl, mock_randint):
        mock_mp, mock_timeline, mock_clip = self._make_mocks()
        mock_get_mp.return_value = mock_mp
        mock_get_tl.return_value = mock_timeline

        mock_randint.return_value = 5

        # Сегмент 10с → 2 чанка: off (0-5с), on (5-10с)
        # Без смещения: source_start = 5000мс → frame 125
        result_no_offset = distribute_multicam(
            mock_clip, [(0, 10000)],
            min_interval_sec=5, max_interval_sec=5, fps=25.0,
            audio_offset_ms=0,
        )
        infos_no_offset = mock_mp.AppendToTimeline.call_args[0][0]
        frame_no_offset = infos_no_offset[0]["startFrame"]
        self.assertEqual(frame_no_offset, ms_to_frames(5000, 25.0))

        mock_mp.reset_mock()

        # С offset 2000мс: source_start = 5000+2000 = 7000мс → frame 175
        result_with_offset = distribute_multicam(
            mock_clip, [(0, 10000)],
            min_interval_sec=5, max_interval_sec=5, fps=25.0,
            audio_offset_ms=2000,
        )
        infos_with_offset = mock_mp.AppendToTimeline.call_args[0][0]
        frame_with_offset = infos_with_offset[0]["startFrame"]
        self.assertEqual(frame_with_offset, ms_to_frames(7000, 25.0))

        # Разница должна быть ровно 2000мс в кадрах
        self.assertEqual(
            frame_with_offset - frame_no_offset,
            ms_to_frames(2000, 25.0),
        )

    @patch("core.multicam.random.randint")
    @patch("core.multicam.get_current_timeline")
    @patch("core.multicam.get_media_pool")
    def test_negative_offset_clamped_to_zero(self, mock_get_mp, mock_get_tl, mock_randint):
        mock_mp, mock_timeline, mock_clip = self._make_mocks()
        mock_get_mp.return_value = mock_mp
        mock_get_tl.return_value = mock_timeline

        mock_randint.return_value = 5

        # Сегмент: source_start = 5000мс, offset = -10000мс → max(0, -5000) = 0
        distribute_multicam(
            mock_clip, [(0, 10000)],
            min_interval_sec=5, max_interval_sec=5, fps=25.0,
            audio_offset_ms=-10000,
        )
        infos = mock_mp.AppendToTimeline.call_args[0][0]
        self.assertEqual(infos[0]["startFrame"], 0)  # Clamped to 0

    @patch("core.multicam.random.randint")
    @patch("core.multicam.get_current_timeline")
    @patch("core.multicam.get_media_pool")
    def test_adds_v2_track_if_missing(self, mock_get_mp, mock_get_tl, mock_randint):
        mock_mp, mock_timeline, mock_clip = self._make_mocks()
        mock_timeline.GetTrackCount.return_value = 1  # Только V1
        mock_get_mp.return_value = mock_mp
        mock_get_tl.return_value = mock_timeline

        mock_randint.return_value = 5

        distribute_multicam(
            mock_clip, [(0, 10000)],
            min_interval_sec=5, max_interval_sec=5, fps=25.0,
        )
        mock_timeline.AddTrack.assert_called_once_with("video")

    @patch("core.multicam.random.randint")
    @patch("core.multicam.get_current_timeline")
    @patch("core.multicam.get_media_pool")
    def test_disables_audio_on_v2(self, mock_get_mp, mock_get_tl, mock_randint):
        mock_mp, mock_timeline, mock_clip = self._make_mocks()
        mock_get_mp.return_value = mock_mp
        mock_get_tl.return_value = mock_timeline

        mock_randint.return_value = 5

        distribute_multicam(
            mock_clip, [(0, 10000)],
            min_interval_sec=5, max_interval_sec=5, fps=25.0,
        )
        mock_timeline.SetTrackEnable.assert_called_once_with("audio", 2, False)

    @patch("core.multicam.random.randint")
    @patch("core.multicam.get_current_timeline")
    @patch("core.multicam.get_media_pool")
    def test_append_failure_returns_zero(self, mock_get_mp, mock_get_tl, mock_randint):
        mock_mp, mock_timeline, mock_clip = self._make_mocks()
        mock_mp.AppendToTimeline.return_value = None  # Ошибка размещения
        mock_get_mp.return_value = mock_mp
        mock_get_tl.return_value = mock_timeline

        mock_randint.return_value = 5

        result = distribute_multicam(
            mock_clip, [(0, 10000)],
            min_interval_sec=5, max_interval_sec=5, fps=25.0,
        )
        self.assertEqual(result, 0)

    @patch("core.multicam.random.randint")
    @patch("core.multicam.get_current_timeline")
    @patch("core.multicam.get_media_pool")
    def test_multiple_segments(self, mock_get_mp, mock_get_tl, mock_randint):
        mock_mp, mock_timeline, mock_clip = self._make_mocks()
        mock_get_mp.return_value = mock_mp
        mock_get_tl.return_value = mock_timeline

        mock_randint.return_value = 5

        # Два сегмента по 10с каждый
        # Сегмент 1: off 5с, on 5с → 1 скринкаст
        # Сегмент 2: off 5с, on 5с → 1 скринкаст
        # Но show_screencast чередуется: seg1 starts False,
        # seg1 ends at show=True (after 2 toggles), seg2 continues from True
        result = distribute_multicam(
            mock_clip, [(0, 10000), (20000, 30000)],
            min_interval_sec=5, max_interval_sec=5, fps=25.0,
        )
        self.assertGreater(result, 0)

    @patch("core.multicam.random.randint")
    @patch("core.multicam.get_current_timeline")
    @patch("core.multicam.get_media_pool")
    def test_frame_calculations_correct(self, mock_get_mp, mock_get_tl, mock_randint):
        mock_mp, mock_timeline, mock_clip = self._make_mocks()
        mock_get_mp.return_value = mock_mp
        mock_get_tl.return_value = mock_timeline

        mock_randint.return_value = 5
        fps = 25.0

        distribute_multicam(
            mock_clip, [(0, 10000)],
            min_interval_sec=5, max_interval_sec=5, fps=fps,
        )
        infos = mock_mp.AppendToTimeline.call_args[0][0]
        clip = infos[0]

        # Скринкаст: source 5000-10000мс → 125-250 кадров
        self.assertEqual(clip["startFrame"], ms_to_frames(5000, fps))
        expected_duration = ms_to_frames(5000, fps)  # 5с = 125 кадров
        self.assertEqual(clip["endFrame"], clip["startFrame"] + expected_duration)


class TestAutoSwitchIntervals(unittest.TestCase):
    """Тесты для auto_switch_intervals."""

    def test_empty_segments_returns_defaults(self):
        min_iv, max_iv = auto_switch_intervals([])
        self.assertEqual(min_iv, 5)
        self.assertEqual(max_iv, 15)

    def test_none_segments_returns_defaults(self):
        min_iv, max_iv = auto_switch_intervals(None)
        self.assertEqual(min_iv, 5)
        self.assertEqual(max_iv, 15)

    def test_short_segments(self):
        # Средний сегмент 10с → min=3 (10/4=2.5 clamped to 3), max=5
        segments = [(0, 10000), (20000, 30000)]
        min_iv, max_iv = auto_switch_intervals(segments)
        self.assertEqual(min_iv, 3)
        self.assertEqual(max_iv, 5)

    def test_long_segments(self):
        # Средний сегмент 60с → min=15 (60/4), max=30 (60/2)
        segments = [(0, 60000)]
        min_iv, max_iv = auto_switch_intervals(segments)
        self.assertEqual(min_iv, 15)
        self.assertEqual(max_iv, 30)

    def test_very_long_segments_capped(self):
        # Средний 120с → min=30, max=60 but capped to 30
        segments = [(0, 120000)]
        min_iv, max_iv = auto_switch_intervals(segments)
        self.assertEqual(min_iv, 30)
        self.assertEqual(max_iv, 30)

    def test_max_always_greater_than_min(self):
        segments = [(0, 20000)]
        min_iv, max_iv = auto_switch_intervals(segments)
        self.assertGreater(max_iv, min_iv)

    def test_mixed_durations(self):
        # Средний = (5+15+10)/3 = 10с → min=3, max=5
        segments = [(0, 5000), (10000, 25000), (30000, 40000)]
        min_iv, max_iv = auto_switch_intervals(segments)
        self.assertGreaterEqual(min_iv, 3)
        self.assertLessEqual(max_iv, 30)


if __name__ == "__main__":
    unittest.main()
