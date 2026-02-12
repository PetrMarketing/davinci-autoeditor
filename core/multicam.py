"""
Шаг 7: Мультикамерное распределение.
Размещает клипы скринкаста на дорожке V2 через вычисленные интервалы переключения,
чередуя основную камеру (V1) и скринкаст (V2).
"""

import random

from utils.logger import get_logger
from utils.timecode import ms_to_frames
from core.resolve_api import get_media_pool, get_current_timeline, get_fps


def distribute_multicam(
    screencast_clip,
    keep_segments,
    min_interval_sec=5,
    max_interval_sec=15,
    fps=25.0,
):
    """
    Распределить сегменты скринкаста на дорожке V2 текущего таймлайна.

    Алгоритм выбирает случайные точки переключения внутри сохраняемых сегментов,
    размещая клипы скринкаста на V2, где скринкаст должен отображаться.
    V1 (основная камера) присутствует всегда; V2 со скринкастом накладывается поверх, когда активен.

    Аргументы:
        screencast_clip: MediaPoolItem для видео скринкаста.
        keep_segments: Список кортежей (start_ms, end_ms) из шага 6.
        min_interval_sec: Минимальный интервал между переключениями (в секундах).
        max_interval_sec: Максимальный интервал между переключениями (в секундах).
        fps: Частота кадров таймлайна.

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

    log.info("Вычисление точек переключения мультикамеры...")

    # Вычисляем смещение позиции на таймлайне для каждого сохраняемого сегмента
    # Каждый сохраняемый сегмент соответствует позиции на пересобранном таймлайне
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

    log.info(f"Размещение {len(switch_regions)} сегментов скринкаста на V2...")

    # Убеждаемся, что дорожка V2 существует
    track_count = timeline.GetTrackCount("video")
    if track_count < 2:
        timeline.AddTrack("video")
        log.info("Добавлена видеодорожка V2")

    # Формируем информацию о клипах для V2
    clip_infos = []
    for tl_start_ms, tl_end_ms, src_start_ms in switch_regions:
        src_start_frame = ms_to_frames(src_start_ms, fps)
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

    # Отключаем аудио на V2 (звук скринкаста не нужен, если синхронизирован на V1)
    timeline.SetTrackEnable("audio", 2, False)
    log.info("Аудио на дорожке V2 отключено")

    return len(clip_infos)
