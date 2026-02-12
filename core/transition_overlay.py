"""
Шаг 9: Наложение видеопереходов на V3 с режимом наложения Add.
Размещает готовые видеоклипы переходов в точках склейки на верхней видеодорожке.
"""

import os

from utils.logger import get_logger
from utils.timecode import ms_to_frames
from core.resolve_api import (
    get_media_pool, get_current_timeline, get_fps,
    find_bin, get_clip_duration_frames,
)

# Константы режимов наложения Resolve
COMPOSITE_NORMAL = 0
COMPOSITE_ADD = 5
COMPOSITE_SCREEN = 8
COMPOSITE_OVERLAY = 9


def import_transition_video(transition_path):
    """
    Импортировать видеофайл перехода в медиапул.

    Аргументы:
        transition_path: Путь к файлу перехода .mov/.mp4.

    Возвращает:
        MediaPoolItem для клипа перехода.
    """
    log = get_logger()
    mp = get_media_pool()

    if not transition_path or not os.path.isfile(transition_path):
        raise FileNotFoundError(f"Видео перехода не найдено: {transition_path}")

    # Импортируем в бин «AutoEditor/Transitions»
    ae_bin = find_bin("AutoEditor")
    tr_bin = find_bin("Transitions", ae_bin)
    mp.SetCurrentFolder(tr_bin)

    clips = mp.ImportMedia([transition_path])
    if not clips or len(clips) == 0:
        raise RuntimeError(f"Не удалось импортировать переход: {transition_path}")

    log.info(f"Видео перехода импортировано: {clips[0].GetName()}")
    return clips[0]


def apply_transitions(transition_clip, fps=25.0):
    """
    Разместить наложения переходов на V3 в каждой точке склейки на V1.

    Каждый клип перехода центрируется относительно точки склейки и размещается на V3
    с режимом наложения Add для эффекта световой вспышки/перехода.

    Аргументы:
        transition_clip: MediaPoolItem для видео перехода.
        fps: Частота кадров таймлайна.

    Возвращает:
        Количество размещённых переходов.
    """
    log = get_logger()
    mp = get_media_pool()
    timeline = get_current_timeline()

    if not timeline:
        raise RuntimeError("Нет активного таймлайна для переходов")

    v1_items = timeline.GetItemListInTrack("video", 1)
    if not v1_items or len(v1_items) < 2:
        log.info("Менее 2 клипов на V1 — нет точек склейки для переходов")
        return 0

    # Получаем длительность клипа перехода
    tr_duration_frames = get_clip_duration_frames(transition_clip)
    tr_half = tr_duration_frames // 2

    log.info(
        f"Клип перехода: {transition_clip.GetName()}, "
        f"длительность: {tr_duration_frames} кадров"
    )

    # Убеждаемся, что дорожка V3 существует
    track_count = timeline.GetTrackCount("video")
    while track_count < 3:
        timeline.AddTrack("video")
        track_count += 1
    log.info("Дорожка V3 готова для переходов")

    # Находим точки склейки (конец каждого клипа, кроме последнего)
    cut_points = []
    for item in v1_items[:-1]:
        cut_frame = item.GetEnd()
        cut_points.append(cut_frame)

    log.info(f"Найдено {len(cut_points)} точек склейки")

    # Размещаем клипы переходов в каждой точке склейки
    clip_infos = []
    for cut_frame in cut_points:
        # Центрируем переход относительно точки склейки
        tl_start = max(0, cut_frame - tr_half)

        clip_info = {
            "mediaPoolItem": transition_clip,
            "startFrame": 0,
            "endFrame": tr_duration_frames,
            "trackIndex": 3,
            "recordFrame": tl_start,
            "mediaType": 1,
        }
        clip_infos.append(clip_info)

    result = mp.AppendToTimeline(clip_infos)
    if not result:
        log.error("Не удалось разместить клипы переходов на V3")
        return 0

    # Применяем режим наложения Add ко всем клипам на V3
    v3_items = timeline.GetItemListInTrack("video", 3)
    if v3_items:
        for item in v3_items:
            item.SetProperty("CompositeMode", COMPOSITE_ADD)
            # Делаем переход полупрозрачным при необходимости
            item.SetProperty("Opacity", 80.0)

        log.info(f"Режим наложения Add применён к {len(v3_items)} клипам переходов на V3")

    # Отключаем аудио дорожки переходов
    timeline.SetTrackEnable("audio", 3, False)

    log.info(f"Шаг 9 завершён: размещено {len(cut_points)} переходов")
    return len(cut_points)
