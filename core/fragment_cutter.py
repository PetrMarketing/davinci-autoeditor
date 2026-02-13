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


def rebuild_timeline(main_clip, keep_segments, timeline_name, fps=25.0,
                     screencast_clip=None, audio_offset_ms=0):
    """
    Создание нового таймлайна из сохраняемых сегментов на V1 (основное видео)
    и V2 (скринкаст). Имитирует blade+ripple delete на обеих дорожках.

    Args:
        main_clip: MediaPoolItem основного видео.
        keep_segments: Список кортежей (start_ms, end_ms).
        timeline_name: Имя нового таймлайна.
        fps: FPS таймлайна.
        screencast_clip: MediaPoolItem скринкаста (необязательно).
        audio_offset_ms: Смещение аудио скринкаста в мс (из шага 2).

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

    # V1: основное видео — все сохраняемые сегменты
    clip_infos = []
    for start_ms, end_ms in keep_segments:
        clip_info = {
            "mediaPoolItem": main_clip,
            "startFrame": ms_to_frames(start_ms, fps),
            "endFrame": ms_to_frames(end_ms, fps),
            "trackIndex": 1,
            "mediaType": 1,
        }
        clip_infos.append(clip_info)

    result = mp.AppendToTimeline(clip_infos)
    if result:
        log.info(f"Добавлено {len(clip_infos)} сегментов основного видео на V1")
    else:
        log.error("AppendToTimeline завершился с ошибкой")
        raise RuntimeError("Не удалось добавить сегменты в таймлайн")

    # V2: скринкаст — те же сегменты со смещением аудио (blade+ripple на обеих дорожках)
    if screencast_clip:
        log.info("Добавление скринкаста на V2 (те же сегменты со смещением)...")
        if new_tl.GetTrackCount("video") < 2:
            new_tl.AddTrack("video")

        sc_infos = []
        for start_ms, end_ms in keep_segments:
            src_start_ms = max(0, start_ms + audio_offset_ms)
            src_end_ms = max(0, end_ms + audio_offset_ms)
            sc_info = {
                "mediaPoolItem": screencast_clip,
                "startFrame": ms_to_frames(src_start_ms, fps),
                "endFrame": ms_to_frames(src_end_ms, fps),
                "trackIndex": 2,
                "mediaType": 1,
            }
            sc_infos.append(sc_info)

        sc_result = mp.AppendToTimeline(sc_infos)
        if sc_result:
            log.info(f"Добавлено {len(sc_infos)} сегментов скринкаста на V2")
            new_tl.SetTrackEnable("audio", 2, False)
            log.info("Аудио на V2 отключено")
        else:
            log.warning("Не удалось добавить сегменты скринкаста на V2")

    # Проверка
    item_count = new_tl.GetTrackCount("video")
    log.info(f"Таймлайн '{timeline_name}' создан, видеодорожек: {item_count}")

    total_frames = 0
    items = new_tl.GetItemListInTrack("video", 1)
    if items:
        total_frames = sum(item.GetDuration() for item in items)
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
