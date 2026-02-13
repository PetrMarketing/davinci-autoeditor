"""
Шаг 7: Мультикамерное распределение.
Размещает клипы скринкаста на дорожке V2 через вычисленные интервалы переключения,
чередуя основную камеру (V1) и скринкаст (V2).
"""

import random

from utils.logger import get_logger
from utils.timecode import ms_to_frames
from core.resolve_api import get_media_pool, get_current_timeline, get_fps


def auto_switch_intervals(keep_segments):
    """
    Автоматически рассчитать интервалы переключения на основе длительности сегментов.

    Логика: берём среднюю длительность сегмента, делим на 3-4 части.
    Минимальный интервал = средняя / 4, максимальный = средняя / 2.
    Ограничения: мин 3с, макс 30с.

    Возвращает:
        Кортеж (min_interval_sec, max_interval_sec).
    """
    log = get_logger()

    if not keep_segments:
        log.info("Нет сегментов — используются интервалы по умолчанию (5-15с)")
        return 5, 15

    durations = [(end - start) / 1000.0 for start, end in keep_segments]
    avg_dur = sum(durations) / len(durations)

    min_iv = max(3, int(round(avg_dur / 4)))
    max_iv = max(min_iv + 1, int(round(avg_dur / 2)))
    max_iv = min(max_iv, 30)

    log.info(f"Автоинтервалы переключения: {min_iv}-{max_iv}с "
             f"(средний сегмент: {avg_dur:.1f}с)")
    return min_iv, max_iv


def distribute_multicam(
    screencast_clip,
    keep_segments,
    min_interval_sec=5,
    max_interval_sec=15,
    fps=25.0,
    audio_offset_ms=0,
):
    """
    Мультикамерное распределение скринкаста на дорожке V2.

    V2 уже содержит все сегменты скринкаста (добавлены на шаге 6).
    Мультикамера удаляет V2-клипы, где должна быть основная камера,
    оставляя только интервалы переключения на скринкаст.

    Аргументы:
        screencast_clip: MediaPoolItem для видео скринкаста.
        keep_segments: Список кортежей (start_ms, end_ms) из шага 6.
        min_interval_sec: Минимальный интервал между переключениями (в секундах).
        max_interval_sec: Максимальный интервал между переключениями (в секундах).
        fps: Частота кадров таймлайна.
        audio_offset_ms: Смещение аудио скринкаста (в мс) из шага 2.

    Возвращает:
        Количество сегментов скринкаста, размещённых на V2.
    """
    log = get_logger()
    mp = get_media_pool()
    timeline = get_current_timeline()

    if not timeline:
        raise RuntimeError("Нет активного таймлайна для мультикамерного распределения")

    if not screencast_clip:
        log.info("Клип скринкаста отсутствует — пропускаем мультикамерное распределение")
        return 0

    if audio_offset_ms:
        log.info(f"Применяется смещение аудио: {audio_offset_ms} мс")

    log.info("Вычисление точек переключения мультикамеры...")

    timeline_pos_ms = 0
    switch_regions = []  # (timeline_start_ms, timeline_end_ms, source_start_ms)
    show_screencast = False

    for seg_start_ms, seg_end_ms in keep_segments:
        seg_duration_ms = seg_end_ms - seg_start_ms
        seg_offset = 0

        while seg_offset < seg_duration_ms:
            interval_ms = random.randint(min_interval_sec, max_interval_sec) * 1000
            chunk_end = min(seg_offset + interval_ms, seg_duration_ms)

            if show_screencast:
                switch_regions.append((
                    timeline_pos_ms + seg_offset,
                    timeline_pos_ms + chunk_end,
                    seg_start_ms + seg_offset,
                ))

            show_screencast = not show_screencast
            seg_offset = chunk_end

        timeline_pos_ms += seg_duration_ms

    log.info(f"Мультикамера: {len(switch_regions)} интервалов скринкаста")

    # Удаляем существующие клипы с V2 (размещены на шаге 6)
    track_count = timeline.GetTrackCount("video")
    if track_count >= 2:
        v2_items = timeline.GetItemListInTrack("video", 2)
        if v2_items:
            for item in v2_items:
                timeline.DeleteTimelineItem(item)
            log.info(f"Удалено {len(v2_items)} клипов с V2 для пересборки мультикамеры")
    else:
        timeline.AddTrack("video")
        log.info("Добавлена видеодорожка V2")

    # Размещаем только выбранные интервалы скринкаста на V2
    clip_infos = []
    for tl_start_ms, tl_end_ms, src_start_ms in switch_regions:
        src_start_frame = ms_to_frames(max(0, src_start_ms + audio_offset_ms), fps)
        duration_frames = ms_to_frames(tl_end_ms - tl_start_ms, fps)
        src_end_frame = src_start_frame + duration_frames

        clip_info = {
            "mediaPoolItem": screencast_clip,
            "startFrame": src_start_frame,
            "endFrame": src_end_frame,
            "trackIndex": 2,
            "mediaType": 1,
        }
        clip_infos.append(clip_info)

    if clip_infos:
        result = mp.AppendToTimeline(clip_infos)
        if result:
            log.info(f"Размещено {len(clip_infos)} сегментов скринкаста на V2")
        else:
            log.error("Не удалось разместить сегменты скринкаста на V2")
            return 0

    timeline.SetTrackEnable("audio", 2, False)
    log.info("Аудио на дорожке V2 отключено")

    return len(clip_infos)
