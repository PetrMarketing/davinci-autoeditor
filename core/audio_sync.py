"""
Шаг 2: Синхронизация аудио по звуковой волне через ffmpeg.
Определяет смещение между основным видео и скринкастом по первому звуку,
физически выравнивает V2 на таймлайне (как Automatically Align Clips → Waveform),
сохраняет смещение для шага 8 (мультикамера).
"""

import json
import os
import subprocess
import re

from utils.logger import get_logger
from utils.timecode import ms_to_frames


def _detect_first_sound(file_path, threshold_db=-30):
    """Определить момент первого звука в файле через ffmpeg silencedetect."""
    log = get_logger()

    if not os.path.isfile(file_path):
        log.warning(f"  Файл не найден: {file_path}")
        return 0.0

    cmd = [
        "ffmpeg", "-i", file_path,
        "-af", f"silencedetect=n={threshold_db}dB:d=0.1",
        "-t", "120", "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr

    if result.returncode != 0 and not output:
        log.warning(f"  ffmpeg ошибка (код {result.returncode}). Проверьте, что ffmpeg установлен.")
        return 0.0

    match = re.search(r"silence_end:\s*([\d.]+)", output)
    if match:
        return float(match.group(1))

    # Проверяем, был ли вообще анализ
    if "silencedetect" not in output:
        log.warning(f"  ffmpeg: silencedetect не запустился для {os.path.basename(file_path)}")

    return 0.0


def auto_sync_audio(clips_dict, config=None):
    """
    Синхронизировать аудио между основным видео и скринкастом по звуковой волне.

    Определяет смещение по моменту первого звука в каждом файле,
    физически выравнивает V2 на таймлайне путём пересоздания таймлайна,
    затем отключает аудио V2.

    Аргументы:
        clips_dict: dict с 'main' и 'screencast' (MediaPoolItem).
        config: объект Config для сохранения смещения.

    Возвращает:
        Смещение в миллисекундах (int).
    """
    log = get_logger()

    main_clip = clips_dict.get("main")
    screencast_clip = clips_dict.get("screencast")

    if not main_clip:
        raise RuntimeError("Основной клип для синхронизации аудио не найден")

    if not screencast_clip:
        log.info("Скринкаст отсутствует — пропуск синхронизации аудио")
        return 0

    log.info("Синхронизация аудио по звуковой волне...")
    log.info(f"  Основной: {main_clip.GetName()}")
    log.info(f"  Скринкаст: {screencast_clip.GetName()}")

    main_path = main_clip.GetClipProperty("File Path") or ""
    sc_path = screencast_clip.GetClipProperty("File Path") or ""

    log.info(f"  Путь основного: {main_path}")
    log.info(f"  Путь скринкаста: {sc_path}")

    if not main_path or not sc_path:
        log.warning("Не удалось получить пути к файлам — пропуск синхронизации")
        return 0

    if not os.path.isfile(main_path):
        log.warning(f"Файл не найден: {main_path}")
        return 0
    if not os.path.isfile(sc_path):
        log.warning(f"Файл не найден: {sc_path}")
        return 0

    # Определяем момент первого звука
    log.info("Анализ звуковой волны основного видео...")
    main_onset = _detect_first_sound(main_path)
    log.info(f"  Первый звук (основное): {main_onset:.3f} с")

    log.info("Анализ звуковой волны скринкаста...")
    sc_onset = _detect_first_sound(sc_path)
    log.info(f"  Первый звук (скринкаст): {sc_onset:.3f} с")

    offset_sec = sc_onset - main_onset
    offset_ms = round(offset_sec * 1000)

    log.info(f"Смещение аудио: {offset_sec:.3f} с ({offset_ms} мс)")

    if abs(offset_ms) < 50:
        log.info("Смещение минимальное — клипы уже синхронизированы")
        offset_ms = 0

    # Физическое выравнивание V2 на таймлайне
    try:
        from core.resolve_api import (
            get_current_timeline, get_current_project, get_media_pool, get_fps,
        )

        timeline = get_current_timeline()
        project = get_current_project()
        mp = get_media_pool()

        if timeline and offset_ms != 0:
            tl_name = timeline.GetName()
            fps = get_fps()
            offset_frames = ms_to_frames(abs(offset_ms), fps)

            log.info("Пересоздание таймлайна с выровненным скринкастом...")

            # Удаляем старый таймлайн и создаём новый с правильным выравниванием
            try:
                mp.DeleteTimelines([timeline])

                new_tl = mp.CreateTimelineFromClips(tl_name, [main_clip])
                if new_tl:
                    project.SetCurrentTimeline(new_tl)
                    start_frame = new_tl.GetStartFrame()

                    if new_tl.GetTrackCount("video") < 2:
                        new_tl.AddTrack("video")

                    clip_info = {
                        "mediaPoolItem": screencast_clip,
                        "trackIndex": 2,
                    }

                    if offset_ms > 0:
                        # Скринкаст начал запись раньше → обрезаем начало скринкаста
                        clip_info["recordFrame"] = start_frame
                        clip_info["startFrame"] = offset_frames
                    else:
                        # Основное видео начало раньше → размещаем скринкаст позже
                        clip_info["recordFrame"] = start_frame + offset_frames

                    sc_ok = mp.AppendToTimeline([clip_info])
                    if sc_ok:
                        log.info(f"Скринкаст выровнен на V2 (смещение: {offset_ms} мс, {offset_frames} кадров)")
                    else:
                        log.warning("Не удалось добавить выровненный скринкаст на V2")
                else:
                    log.warning("Не удалось пересоздать таймлайн")
            except Exception as e:
                log.warning(f"DeleteTimelines не поддерживается — смещение будет применено при мультикамере: {e}")

        elif timeline and offset_ms == 0:
            log.info("Клипы уже синхронизированы — таймлайн не изменён")

        # Отключаем аудио V2
        tl = get_current_timeline()
        if tl and tl.GetTrackCount("audio") >= 2:
            tl.SetTrackEnable("audio", 2, False)
            log.info("Аудио V2 отключено после синхронизации")
    except ImportError:
        pass

    # Сохраняем смещение
    if config:
        config.set("audio_offset_ms", offset_ms)
        config.save()

    working_dir = config.get("working_dir", "") if config else ""
    if working_dir:
        sync_data = {
            "main_onset_sec": main_onset,
            "screencast_onset_sec": sc_onset,
            "offset_ms": offset_ms,
            "offset_sec": offset_sec,
        }
        output_path = os.path.join(working_dir, "audio_sync.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(sync_data, f, indent=2)
        log.info("Данные синхронизации сохранены в audio_sync.json")

    log.info(f"Шаг 2 завершён: смещение {offset_ms} мс")
    return offset_ms
