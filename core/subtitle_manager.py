"""
Шаг 4: Генерация субтитров из аудио с помощью встроенного распознавания речи Resolve,
затем экспорт в SRT для дальнейшей обработки.
"""

import os
import time

from utils.logger import get_logger
from utils.srt_parser import read_srt
from core.resolve_api import get_current_timeline, get_current_project


def generate_subtitles(language="Russian"):
    """
    Генерация субтитров из аудио текущего таймлайна с помощью встроенной
    функции CreateSubtitlesFromAudio в Resolve.

    Args:
        language: Язык для распознавания речи.

    Returns:
        Путь к экспортированному SRT-файлу или None в случае ошибки.
    """
    log = get_logger()
    timeline = get_current_timeline()

    if not timeline:
        raise RuntimeError("Нет активного таймлайна для генерации субтитров")

    log.info(f"Генерация субтитров (язык: {language})...")
    log.info("Это может занять несколько минут в зависимости от длины видео.")

    # Встроенная функция Resolve для создания субтитров из аудио
    result = timeline.CreateSubtitlesFromAudio(
        {
            "language": language,
            "format": "SRT",
        }
    )

    if not result:
        log.warning(
            "CreateSubtitlesFromAudio не вернул результат. "
            "Убедитесь, что используется DaVinci Resolve Studio (не бесплатная версия)."
        )
        return None

    log.info("Генерация субтитров завершена")
    return result


def export_subtitles(working_dir, filename="original.srt"):
    """
    Экспорт субтитров текущего таймлайна в SRT-файл.

    Args:
        working_dir: Директория для сохранения SRT-файла.
        filename: Имя выходного файла.

    Returns:
        Полный путь к экспортированному SRT-файлу.
    """
    log = get_logger()
    timeline = get_current_timeline()

    if not timeline:
        raise RuntimeError("Нет активного таймлайна")

    output_path = os.path.join(working_dir, filename)

    # Экспорт дорожки субтитров в SRT
    result = timeline.ExportSubtitles(output_path, "SRT")
    if result:
        log.info(f"Субтитры экспортированы в: {output_path}")
    else:
        # Запасной вариант: попытка извлечь из элементов дорожки субтитров
        log.warning("ExportSubtitles не удался, попытка ручного извлечения...")
        _extract_subtitles_manual(timeline, output_path)

    # Проверка результата
    if os.path.exists(output_path):
        blocks = read_srt(output_path)
        log.info(f"Экспортировано {len(blocks)} блоков субтитров")
        return output_path
    else:
        raise RuntimeError("Не удалось экспортировать субтитры")


def _extract_subtitles_manual(timeline, output_path):
    """
    Запасной вариант: ручное извлечение субтитров из элементов дорожки субтитров таймлайна.
    """
    log = get_logger()
    # Получение элементов дорожки субтитров
    sub_track_count = timeline.GetTrackCount("subtitle")
    if sub_track_count == 0:
        raise RuntimeError("В таймлайне не найдены дорожки субтитров")

    items = timeline.GetItemListInTrack("subtitle", 1)
    if not items:
        raise RuntimeError("В дорожке не найдены элементы субтитров")

    from utils.timecode import ms_to_timecode
    from core.resolve_api import get_fps

    fps = get_fps()

    with open(output_path, "w", encoding="utf-8") as f:
        for i, item in enumerate(items, 1):
            start_frame = item.GetStart()
            end_frame = item.GetEnd()
            text = item.GetName() or ""

            start_ms = int(round(start_frame / fps * 1000))
            end_ms = int(round(end_frame / fps * 1000))

            start_tc = ms_to_timecode(start_ms)
            end_tc = ms_to_timecode(end_ms)

            f.write(f"{i}\n")
            f.write(f"{start_tc} --> {end_tc}\n")
            f.write(f"{text}\n\n")

    log.info(f"Вручную извлечено {len(items)} блоков субтитров")


def import_srt_to_timeline(srt_path):
    """Импорт SRT-файла обратно в текущий таймлайн как дорожку субтитров."""
    log = get_logger()
    timeline = get_current_timeline()

    if not timeline:
        raise RuntimeError("Нет активного таймлайна")

    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"SRT-файл не найден: {srt_path}")

    result = timeline.ImportSubtitles(srt_path)
    if result:
        log.info(f"Субтитры импортированы из: {srt_path}")
    else:
        log.warning("ImportSubtitles не вернул результат")

    return result
