"""
Шаг 3: Обнаружение участков тишины в аудиодорожке видео с помощью pydub + ffmpeg.
Только обнаруживает — НЕ вырезает. Вырезка объединяется с результатами ИИ на шаге 6.
"""

import json
import os
import subprocess
import tempfile

from utils.logger import get_logger


def auto_detect_threshold(video_path):
    """
    Автоматически определить порог тишины по средней громкости файла.

    Использует ffmpeg volumedetect для получения mean_volume,
    затем устанавливает порог = mean_volume + 3 дБ.

    Возвращает:
        Порог в дБ (int), например -35.
    """
    log = get_logger()
    log.info("Автоопределение порога тишины...")

    if not os.path.isfile(video_path):
        log.warning(f"  Файл не найден: {video_path} — используется -40 дБ")
        return -40

    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", "volumedetect",
        "-f", "null", "-",
    ]
    import re
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr

    match = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", output)
    if match:
        mean_vol = float(match.group(1))
        threshold = int(round(mean_vol + 3))
        log.info(f"  Средняя громкость: {mean_vol:.1f} дБ → порог: {threshold} дБ")
        return threshold

    log.warning("  Не удалось определить громкость — используется -40 дБ")
    return -40


def detect_silence(video_path, threshold_db=-40, min_duration_ms=500, working_dir=""):
    """
    Обнаружить участки тишины в аудиодорожке видеофайла.

    Аргументы:
        video_path: Путь к видеофайлу.
        threshold_db: Порог громкости, ниже которого звук считается тишиной (дБ).
        min_duration_ms: Минимальная длительность тишины для регистрации (мс).
        working_dir: Директория для сохранения результатов.

    Возвращает:
        Список кортежей (начало_мс, конец_мс), представляющих участки тишины.
    """
    log = get_logger()
    log.info(f"Обнаружение тишины в: {os.path.basename(video_path)}")
    log.info(f"  Полный путь: {video_path}")
    log.info(f"  Порог: {threshold_db} дБ, мин. длительность: {min_duration_ms} мс")

    if not os.path.isfile(video_path):
        log.error(f"  Файл не найден: {video_path}")
        return []

    # Извлечение аудио в WAV с помощью ffmpeg
    wav_path = tempfile.mktemp(suffix=".wav")
    try:
        log.info("Извлечение аудиодорожки через ffmpeg...")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                wav_path,
            ],
            capture_output=True,
            check=True,
        )

        # Используем pydub для обнаружения тишины
        from pydub import AudioSegment
        from pydub.silence import detect_silence as pydub_detect

        log.info("Анализ аудио на наличие участков тишины...")
        audio = AudioSegment.from_wav(wav_path)
        total_duration_ms = len(audio)

        # pydub.silence.detect_silence возвращает список [начало, конец] в мс
        silence_ranges = pydub_detect(
            audio,
            min_silence_len=min_duration_ms,
            silence_thresh=threshold_db,
        )

        silence_regions = [(s, e) for s, e in silence_ranges]

        log.info(
            f"Найдено участков тишины: {len(silence_regions)} "
            f"(общая длительность аудио: {total_duration_ms / 1000:.1f}с)"
        )

        # Подсчёт общей длительности тишины
        total_silence_ms = sum(e - s for s, e in silence_regions)
        log.info(f"Общая тишина: {total_silence_ms / 1000:.1f}с "
                 f"({total_silence_ms / total_duration_ms * 100:.1f}%)")

        # Сохранение в JSON
        if working_dir:
            output_path = os.path.join(working_dir, "silence_regions.json")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "video": video_path,
                        "threshold_db": threshold_db,
                        "min_duration_ms": min_duration_ms,
                        "total_duration_ms": total_duration_ms,
                        "regions": silence_regions,
                    },
                    f,
                    indent=2,
                )
            log.info(f"Участки тишины сохранены в: {output_path}")

        return silence_regions

    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


def load_silence_regions(working_dir):
    """Загрузить ранее обнаруженные участки тишины из JSON."""
    path = os.path.join(working_dir, "silence_regions.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [tuple(r) for r in data.get("regions", [])]


def place_silence_markers(silence_regions):
    """
    Расставить маркеры на таймлайне в местах тишины (как в AutoCut).
    Красные маркеры показывают участки тишины для визуального контроля перед нарезкой.

    Args:
        silence_regions: Список кортежей (start_ms, end_ms).

    Returns:
        Количество расставленных маркеров.
    """
    log = get_logger()

    try:
        from core.resolve_api import get_current_timeline, get_fps
        from utils.timecode import ms_to_frames
    except ImportError:
        log.warning("Не удалось импортировать Resolve API для расстановки маркеров")
        return 0

    timeline = get_current_timeline()
    if not timeline:
        log.warning("Нет активного таймлайна для расстановки маркеров")
        return 0

    fps = get_fps()
    timeline_start = timeline.GetStartFrame()

    # Удаляем старые маркеры тишины
    try:
        timeline.DeleteMarkerByCustomData("AutoEditor:silence")
    except Exception:
        pass

    count = 0
    for region in silence_regions:
        start_frame = timeline_start + ms_to_frames(region[0], fps)
        dur_frames = max(ms_to_frames(region[1] - region[0], fps), 1)
        dur_sec = (region[1] - region[0]) / 1000

        try:
            ok = timeline.AddMarker(
                start_frame, "Red",
                f"Тишина {dur_sec:.1f}с",
                f"{region[0] / 1000:.1f} - {region[1] / 1000:.1f} сек",
                dur_frames, "AutoEditor:silence",
            )
            if ok:
                count += 1
        except Exception:
            pass

    log.info(f"Расставлено {count} маркеров тишины на таймлайне (красные)")
    return count
