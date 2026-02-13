"""
Нарезка таймлайна из сохраняемых сегментов.

Шаг 4: Нарезка тишины — удаляет только паузы.
Шаг 7: Нарезка мусора — удаляет ИИ-помеченные блоки (таймкоды маппятся
       с чистого таймлайна на оригинальное видео).
"""

import json
import os

from utils.logger import get_logger
from utils.srt_parser import read_srt, invert_regions
from utils.timecode import ms_to_frames
from core.resolve_api import (
    get_media_pool, create_timeline, get_fps,
)
from core.silence_remover import load_silence_regions


def compute_silence_keep_segments(working_dir, total_duration_ms, fps=25.0):
    """
    Шаг 4: Вычисление сегментов для сохранения (только по тишине, без ИИ).
    Сохраняет результат в keep_segments_silence.json.
    """
    log = get_logger()

    silence_regions = load_silence_regions(working_dir)
    log.info(f"Загружено {len(silence_regions)} регионов тишины")

    keep_segments = invert_regions(silence_regions, total_duration_ms)
    log.info(f"Сегментов для сохранения: {len(keep_segments)}")

    kept_ms = sum(e - s for s, e in keep_segments)
    removed_ms = total_duration_ms - kept_ms
    pct = (removed_ms / total_duration_ms * 100) if total_duration_ms > 0 else 0
    log.info(
        f"Сохраняется {kept_ms / 1000:.1f}с, удаляется {removed_ms / 1000:.1f}с тишины "
        f"({pct:.1f}% вырезано)"
    )

    output_path = os.path.join(working_dir, "keep_segments_silence.json")
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


def clean_to_original(t_clean_ms, keep_segments):
    """
    Маппинг времени с чистого таймлайна (без тишины) на оригинальное видео.

    Args:
        t_clean_ms: Позиция на чистом таймлайне (мс).
        keep_segments: Список (start_ms, end_ms) сегментов тишины.

    Returns:
        Позиция в оригинальном видео (мс).
    """
    elapsed = 0
    for seg_start, seg_end in keep_segments:
        seg_dur = seg_end - seg_start
        if elapsed + seg_dur >= t_clean_ms:
            return seg_start + (t_clean_ms - elapsed)
        elapsed += seg_dur
    # За пределами — конец последнего сегмента
    if keep_segments:
        return keep_segments[-1][1]
    return t_clean_ms


def compute_ai_keep_segments(working_dir, total_duration_ms, fps=25.0):
    """
    Шаг 7: Вычисление финальных сегментов (тишина + ИИ-удаления).
    Маппит ИИ-таймкоды с чистого таймлайна на оригинальное время,
    объединяет с регионами тишины, сохраняет в keep_segments.json.
    """
    log = get_logger()

    # Загрузка silence-only keep segments (от шага 4)
    silence_keep_path = os.path.join(working_dir, "keep_segments_silence.json")
    silence_keep = []
    if os.path.exists(silence_keep_path):
        with open(silence_keep_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        silence_keep = [tuple(s) for s in data.get("segments", [])]
    log.info(f"Загружено {len(silence_keep)} сегментов после нарезки тишины")

    # Загрузка ИИ-очищенных субтитров
    cleaned_srt_path = os.path.join(working_dir, "cleaned.srt")
    if not os.path.exists(cleaned_srt_path):
        log.warning("Файл cleaned.srt не найден — используются сегменты тишины без изменений")
        # Копируем silence keep как финальные
        if os.path.exists(silence_keep_path):
            import shutil
            shutil.copy2(silence_keep_path, os.path.join(working_dir, "keep_segments.json"))
        return silence_keep

    ai_blocks = read_srt(cleaned_srt_path)
    deleted_count = sum(1 for b in ai_blocks if b.deleted)
    log.info(f"ИИ пометил {deleted_count}/{len(ai_blocks)} блоков на удаление")

    # Маппим ИИ-удаления с чистого таймлайна на оригинальное время
    ai_delete_regions = []
    for b in ai_blocks:
        if b.deleted:
            orig_start = clean_to_original(b.start_ms, silence_keep)
            orig_end = clean_to_original(b.end_ms, silence_keep)
            ai_delete_regions.append((orig_start, orig_end))
    log.info(f"ИИ-удалений (в оригинальном времени): {len(ai_delete_regions)}")

    # Объединяем тишину + ИИ-удаления
    silence_regions = load_silence_regions(working_dir)
    all_delete = list(silence_regions) + ai_delete_regions

    # Сортируем и объединяем пересечения
    all_delete.sort(key=lambda r: r[0])
    merged = []
    for r in all_delete:
        if not merged or r[0] > merged[-1][1]:
            merged.append([r[0], r[1]])
        else:
            merged[-1][1] = max(merged[-1][1], r[1])
    merged_tuples = [(s, e) for s, e in merged]

    keep_segments = invert_regions(merged_tuples, total_duration_ms)
    log.info(f"Финальных сегментов для сохранения: {len(keep_segments)}")

    kept_ms = sum(e - s for s, e in keep_segments)
    removed_ms = total_duration_ms - kept_ms
    pct = (removed_ms / total_duration_ms * 100) if total_duration_ms > 0 else 0
    log.info(
        f"Итого: сохраняется {kept_ms / 1000:.1f}с, удаляется {removed_ms / 1000:.1f}с "
        f"({pct:.1f}% вырезано)"
    )

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
    """
    log = get_logger()
    mp = get_media_pool()

    log.info(f"Пересборка таймлайна '{timeline_name}' из {len(keep_segments)} сегментов...")

    new_tl = create_timeline(timeline_name)
    if not new_tl:
        raise RuntimeError(f"Не удалось создать таймлайн: {timeline_name}")

    # V1: основное видео
    clip_infos = []
    for start_ms, end_ms in keep_segments:
        clip_infos.append({
            "mediaPoolItem": main_clip,
            "startFrame": ms_to_frames(start_ms, fps),
            "endFrame": ms_to_frames(end_ms, fps),
            "trackIndex": 1,
            "mediaType": 1,
        })

    result = mp.AppendToTimeline(clip_infos)
    if result:
        log.info(f"Добавлено {len(clip_infos)} сегментов основного видео на V1")
    else:
        log.error("AppendToTimeline завершился с ошибкой")
        raise RuntimeError("Не удалось добавить сегменты в таймлайн")

    # V2: скринкаст
    if screencast_clip:
        log.info("Добавление скринкаста на V2 (те же сегменты со смещением)...")
        if new_tl.GetTrackCount("video") < 2:
            new_tl.AddTrack("video")

        sc_infos = []
        for start_ms, end_ms in keep_segments:
            sc_infos.append({
                "mediaPoolItem": screencast_clip,
                "startFrame": ms_to_frames(max(0, start_ms + audio_offset_ms), fps),
                "endFrame": ms_to_frames(max(0, end_ms + audio_offset_ms), fps),
                "trackIndex": 2,
                "mediaType": 1,
            })

        sc_result = mp.AppendToTimeline(sc_infos)
        if sc_result:
            log.info(f"Добавлено {len(sc_infos)} сегментов скринкаста на V2")
            new_tl.SetTrackEnable("audio", 2, False)
            log.info("Аудио на V2 отключено")
        else:
            log.warning("Не удалось добавить сегменты скринкаста на V2")

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
