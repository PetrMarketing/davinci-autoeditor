"""
Парсер, генератор и утилиты сравнения SRT-файлов субтитров.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .timecode import timecode_to_ms, ms_to_timecode


@dataclass
class SubtitleBlock:
    """Одна запись (блок) субтитров в формате SRT."""
    index: int
    start_ms: int
    end_ms: int
    text: str
    deleted: bool = False


def parse_srt(content: str) -> List[SubtitleBlock]:
    """Разобрать содержимое SRT-строки в список SubtitleBlock."""
    blocks = []
    # Разделение по двойному переводу строки (пустая строка между блоками)
    raw_blocks = re.split(r"\n\s*\n", content.strip())
    for raw in raw_blocks:
        lines = raw.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0].strip())
        except ValueError:
            continue
        # Разбор строки таймкода
        tc_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            lines[1].strip(),
        )
        if not tc_match:
            continue
        start_ms = timecode_to_ms(tc_match.group(1))
        end_ms = timecode_to_ms(tc_match.group(2))
        text = "\n".join(lines[2:]).strip()
        # Проверка наличия маркера [DELETE]
        deleted = "[DELETE]" in text
        if deleted:
            text = text.replace("[DELETE]", "").strip()
        blocks.append(SubtitleBlock(index, start_ms, end_ms, text, deleted))
    return blocks


def read_srt(filepath: str) -> List[SubtitleBlock]:
    """Прочитать и разобрать SRT-файл."""
    with open(filepath, "r", encoding="utf-8") as f:
        return parse_srt(f.read())


def write_srt(blocks: List[SubtitleBlock], filepath: str):
    """Записать блоки субтитров в SRT-файл."""
    with open(filepath, "w", encoding="utf-8") as f:
        for i, block in enumerate(blocks, 1):
            start_tc = ms_to_timecode(block.start_ms)
            end_tc = ms_to_timecode(block.end_ms)
            prefix = "[DELETE] " if block.deleted else ""
            f.write(f"{i}\n")
            f.write(f"{start_tc} --> {end_tc}\n")
            f.write(f"{prefix}{block.text}\n\n")


def get_keep_segments(blocks: List[SubtitleBlock]) -> List[tuple]:
    """
    Из списка блоков (часть помечена удалёнными) вернуть сегменты (start_ms, end_ms),
    которые нужно СОХРАНИТЬ — то есть неудалённые блоки, объединённые
    при соседнем расположении.
    """
    keep = [b for b in blocks if not b.deleted]
    if not keep:
        return []

    segments = []
    current_start = keep[0].start_ms
    current_end = keep[0].end_ms

    for block in keep[1:]:
        # Объединяем, если промежуток маленький (< 200 мс)
        if block.start_ms - current_end < 200:
            current_end = block.end_ms
        else:
            segments.append((current_start, current_end))
            current_start = block.start_ms
            current_end = block.end_ms

    segments.append((current_start, current_end))
    return segments


def merge_silence_and_ai(
    silence_regions: List[tuple],
    ai_blocks: List[SubtitleBlock],
) -> List[tuple]:
    """
    Объединить области тишины и удалённые ИИ блоки субтитров
    в единый список регионов на удаление (start_ms, end_ms).
    Возвращает отсортированные и объединённые регионы удаления.
    """
    delete_regions = list(silence_regions)

    for block in ai_blocks:
        if block.deleted:
            delete_regions.append((block.start_ms, block.end_ms))

    if not delete_regions:
        return []

    # Сортировка и объединение пересекающихся регионов
    delete_regions.sort(key=lambda r: r[0])
    merged = [delete_regions[0]]
    for start, end in delete_regions[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    return merged


def invert_regions(delete_regions: List[tuple], total_duration_ms: int) -> List[tuple]:
    """Преобразовать регионы удаления в регионы сохранения в диапазоне 0..total_duration_ms."""
    if not delete_regions:
        return [(0, total_duration_ms)]

    keep = []
    prev_end = 0
    for start, end in sorted(delete_regions, key=lambda r: r[0]):
        if start > prev_end:
            keep.append((prev_end, start))
        prev_end = max(prev_end, end)

    if prev_end < total_duration_ms:
        keep.append((prev_end, total_duration_ms))

    return keep


def chunk_blocks(blocks: List[SubtitleBlock], chunk_size: int = 50) -> List[List[SubtitleBlock]]:
    """Разбить блоки субтитров на части для обработки ИИ."""
    chunks = []
    for i in range(0, len(blocks), chunk_size):
        chunks.append(blocks[i:i + chunk_size])
    return chunks
