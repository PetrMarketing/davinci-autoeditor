"""
Шаг 10: Титульные карточки глав, генерируемые через ffmpeg drawtext.
Создаёт короткие видеоклипы с текстовым наложением на фоне,
затем импортирует и размещает их в начальных позициях глав.
"""

import json
import os
import subprocess

from utils.logger import get_logger
from utils.timecode import ms_to_frames
from core.resolve_api import (
    get_media_pool, get_current_timeline, get_fps, find_bin,
)

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
STYLES_FILE = os.path.join(ASSETS_DIR, "titles", "styles.json")

DEFAULT_STYLE = {
    "font": "Arial",
    "fontsize": 72,
    "fontcolor": "white",
    "borderw": 3,
    "bordercolor": "black",
    "duration_sec": 3,
    "width": 1920,
    "height": 1080,
    "bg_color": "black",
}


def load_style(style_name="default"):
    """Загрузить пресет стиля текста из styles.json."""
    if os.path.exists(STYLES_FILE):
        try:
            with open(STYLES_FILE, "r", encoding="utf-8") as f:
                styles = json.load(f)
            if style_name in styles:
                merged = dict(DEFAULT_STYLE)
                merged.update(styles[style_name])
                return merged
        except (json.JSONDecodeError, IOError):
            pass
    return dict(DEFAULT_STYLE)


def generate_title_card(
    text,
    output_path,
    background_path="",
    style_name="default",
):
    """
    Сгенерировать видеоклип титульной карточки с помощью ffmpeg drawtext.

    Аргументы:
        text: Текст заголовка для отображения.
        output_path: Путь для выходного файла .mp4.
        background_path: Необязательный путь к фоновому видео/изображению.
        style_name: Название пресета стиля текста.

    Возвращает:
        Путь к сгенерированному видеофайлу.
    """
    log = get_logger()
    style = load_style(style_name)

    duration = style["duration_sec"]
    w = style["width"]
    h = style["height"]

    # Экранируем текст для ffmpeg drawtext (двоеточие, обратный слеш, одинарная кавычка)
    escaped_text = (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )

    drawtext_filter = (
        f"drawtext=text='{escaped_text}'"
        f":fontfile=''"
        f":font='{style['font']}'"
        f":fontsize={style['fontsize']}"
        f":fontcolor={style['fontcolor']}"
        f":borderw={style['borderw']}"
        f":bordercolor={style['bordercolor']}"
        f":x=(w-text_w)/2"
        f":y=(h-text_h)/2"
    )

    if background_path and os.path.isfile(background_path):
        # Используем фоновое видео/изображение как основу
        cmd = [
            "ffmpeg", "-y",
            "-i", background_path,
            "-t", str(duration),
            "-vf", f"scale={w}:{h},{drawtext_filter}",
            "-c:v", "libx264", "-preset", "fast",
            "-an",
            output_path,
        ]
    else:
        # Генерируем фон сплошным цветом
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={style['bg_color']}:s={w}x{h}:d={duration}:r=25",
            "-vf", drawtext_filter,
            "-c:v", "libx264", "-preset", "fast",
            "-an",
            output_path,
        ]

    log.debug(f"Команда ffmpeg: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"Ошибка ffmpeg: {result.stderr}")
        raise RuntimeError(f"Не удалось сгенерировать титульную карточку: {result.stderr}")

    log.info(f"Титульная карточка сгенерирована: {output_path}")
    return output_path


def create_chapter_titles(
    chapters,
    working_dir,
    background_path="",
    style_name="default",
    fps=25.0,
):
    """
    Сгенерировать и разместить титульные карточки для каждой главы на таймлайне.

    Аргументы:
        chapters: Список словарей с ключами 'title' и 'start_ms'.
        working_dir: Директория для сгенерированных файлов титульных карточек.
        background_path: Необязательное фоновое видео/изображение.
        style_name: Название пресета стиля текста.
        fps: Частота кадров таймлайна.

    Возвращает:
        Количество размещённых титульных карточек.
    """
    log = get_logger()
    mp = get_media_pool()
    timeline = get_current_timeline()

    if not timeline:
        raise RuntimeError("Нет активного таймлайна для титульных карточек")

    if not chapters:
        log.info("Главы не определены — пропускаем титульные карточки")
        return 0

    # Создаём директорию для титульных карточек
    titles_dir = os.path.join(working_dir, "generated_titles")
    os.makedirs(titles_dir, exist_ok=True)

    # Убеждаемся, что дорожка V4 существует для титульных карточек
    track_count = timeline.GetTrackCount("video")
    while track_count < 4:
        timeline.AddTrack("video")
        track_count += 1

    # Бин для импорта
    ae_bin = find_bin("AutoEditor")
    titles_bin = find_bin("Titles", ae_bin)
    mp.SetCurrentFolder(titles_bin)

    log.info(f"Генерация {len(chapters)} титульных карточек глав...")

    clip_infos = []
    for i, chapter in enumerate(chapters):
        title = chapter.get("title", f"Chapter {i + 1}")
        start_ms = chapter.get("start_ms", 0)

        # Генерируем видео титульной карточки
        card_path = os.path.join(titles_dir, f"title_{i + 1:03d}.mp4")
        generate_title_card(title, card_path, background_path, style_name)

        # Импортируем в медиапул
        clips = mp.ImportMedia([card_path])
        if not clips or len(clips) == 0:
            log.warning(f"Не удалось импортировать титульную карточку: {card_path}")
            continue

        title_clip = clips[0]
        style = load_style(style_name)
        duration_frames = int(style["duration_sec"] * fps)
        start_frame = ms_to_frames(start_ms, fps)

        clip_info = {
            "mediaPoolItem": title_clip,
            "startFrame": 0,
            "endFrame": duration_frames,
            "trackIndex": 4,
            "recordFrame": start_frame,
            "mediaType": 1,
        }
        clip_infos.append(clip_info)

    if clip_infos:
        result = mp.AppendToTimeline(clip_infos)
        if result:
            log.info(f"Размещено {len(clip_infos)} титульных карточек на V4")
        else:
            log.error("Не удалось разместить титульные карточки на таймлайн")
            return 0

    # Отключаем аудио дорожки титров
    timeline.SetTrackEnable("audio", 4, False)

    log.info(f"Шаг 10 завершён: создано {len(clip_infos)} титульных карточек")
    return len(clip_infos)


def detect_chapters_from_subtitles(srt_path, min_gap_ms=5000):
    """
    Автоматическое определение границ глав по паузам в субтитрах.
    Разрыв главы определяется, когда пауза между блоками субтитров превышает min_gap_ms.

    Аргументы:
        srt_path: Путь к файлу SRT.
        min_gap_ms: Минимальная пауза между субтитрами для обозначения разрыва главы.

    Возвращает:
        Список словарей с ключами 'title' и 'start_ms'.
    """
    from utils.srt_parser import read_srt

    blocks = read_srt(srt_path)
    if not blocks:
        return []

    chapters = [{"title": "Introduction", "start_ms": 0}]
    chapter_num = 1

    for i in range(1, len(blocks)):
        gap = blocks[i].start_ms - blocks[i - 1].end_ms
        if gap >= min_gap_ms:
            chapter_num += 1
            # Используем первые несколько слов следующего субтитра как название главы
            text = blocks[i].text.split()[:5]
            title = " ".join(text)
            if len(title) > 40:
                title = title[:37] + "..."
            chapters.append({
                "title": f"Chapter {chapter_num}: {title}",
                "start_ms": blocks[i].start_ms,
            })

    return chapters
