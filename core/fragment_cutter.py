"""
Шаг 6: Пересборка таймлайна из сохраняемых сегментов.
Объединяет результаты обнаружения тишины и удалённых ИИ блоков субтитров,
чтобы определить, какие части оставить, затем создаёт новый таймлайн только из этих сегментов.
"""

import json
import os

from utils.logger import get_logger
from utils.srt_parser import read_srt, merge_silence_and_ai, invert_regions
from utils.timecode import ms_to_frames, frames_to_resolve_tc
from core.resolve_api import (
    get_media_pool, get_current_project, create_timeline,
    get_fps, get_clip_duration_ms,
)
from core.silence_remover import load_silence_regions


def compute_keep_segments(working_dir, total_duration_ms, fps=25.0):
    """
    Вычисление итоговых сегментов для сохранения путём объединения
    регионов тишины и удалений ИИ.

    Args:
        working_dir: Директория, содержащая silence_regions.json и cleaned.srt.
        total_duration_ms: Общая длительность исходного видео в мс.
        fps: FPS таймлайна.

    Returns:
        Список кортежей (start_ms, end_ms) для сохранения.
    """
    log = get_logger()

    # Загрузка регионов тишины
    silence_regions = load_silence_regions(working_dir)
    log.info(f"Загружено {len(silence_regions)} регионов тишины")

    # Загрузка субтитров, очищенных ИИ
    cleaned_srt_path = os.path.join(working_dir, "cleaned.srt")
    if os.path.exists(cleaned_srt_path):
        ai_blocks = read_srt(cleaned_srt_path)
        log.info(f"Загружено {len(ai_blocks)} блоков субтитров, обработанных ИИ")
    else:
        ai_blocks = []
        log.warning("Файл cleaned.srt не найден — используются только регионы тишины")

    # Объединение в единые регионы удаления
    delete_regions = merge_silence_and_ai(silence_regions, ai_blocks)
    log.info(f"Всего регионов удаления после объединения: {len(delete_regions)}")

    # Инверсия для получения сегментов сохранения
    keep_segments = invert_regions(delete_regions, total_duration_ms)
    log.info(f"Сегментов для сохранения: {len(keep_segments)}")

    # Подсчёт сэкономленного времени
    kept_ms = sum(e - s for s, e in keep_segments)
    removed_ms = total_duration_ms - kept_ms
    log.info(
        f"Сохраняется {kept_ms / 1000:.1f}с, удаляется {removed_ms / 1000:.1f}с "
        f"({removed_ms / total_duration_ms * 100:.1f}% вырезано)"
    )

    # Сохранение сегментов для справки
    output_path = os.path.join(working_dir, "keep_segments.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "total_duration_ms": total_duration_ms,
                "kept_ms": kept_ms,
                "removed_ms": removed_ms,
                "segments": keep_segments,
            },
            f,
            indent=2,
        )

    return keep_segments


def rebuild_timeline(main_clip, keep_segments, timeline_name, fps=25.0):
    """
    Создание нового таймлайна только из сохраняемых сегментов основного клипа.

    Args:
        main_clip: MediaPoolItem основного видео.
        keep_segments: Список кортежей (start_ms, end_ms).
        timeline_name: Имя нового таймлайна.
        fps: FPS таймлайна.

    Returns:
        Новый объект Timeline.
    """
    log = get_logger()
    mp = get_media_pool()

    log.info(f"Пересборка таймлайна '{timeline_name}' из {len(keep_segments)} сегментов...")

    # Создание нового таймлайна
    new_tl = create_timeline(timeline_name)
    if not new_tl:
        raise RuntimeError(f"Не удалось создать таймлайн: {timeline_name}")

    # Формирование списка информации о клипах для AppendToTimeline
    clip_infos = []
    for i, (start_ms, end_ms) in enumerate(keep_segments):
        start_frame = ms_to_frames(start_ms, fps)
        end_frame = ms_to_frames(end_ms, fps)

        clip_info = {
            "mediaPoolItem": main_clip,
            "startFrame": start_frame,
            "endFrame": end_frame,
            "trackIndex": 1,
            "mediaType": 1,  # 1 = Видео + Аудио
        }
        clip_infos.append(clip_info)

    # Добавление всех сегментов в новый таймлайн
    result = mp.AppendToTimeline(clip_infos)
    if result:
        log.info(f"Добавлено {len(clip_infos)} сегментов в таймлайн")
    else:
        log.error("AppendToTimeline завершился с ошибкой")
        raise RuntimeError("Не удалось добавить сегменты в таймлайн")

    # Проверка
    item_count = new_tl.GetTrackCount("video")
    log.info(f"Таймлайн '{timeline_name}' создан, видеодорожек: {item_count}")

    total_frames = 0
    items = new_tl.GetItemListInTrack("video", 1)
    if items:
        total_frames = sum(
            item.GetDuration() for item in items
        )
    log.info(f"Всего кадров в новом таймлайне: {total_frames}")

    return new_tl


def load_keep_segments(working_dir):
    """Загрузка ранее вычисленных сегментов сохранения из JSON."""
    path = os.path.join(working_dir, "keep_segments.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [tuple(s) for s in data.get("segments", [])]
