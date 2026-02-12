"""
Шаг 5: Очистка субтитров с помощью ИИ через OpenRouter API.
Отправляет блоки субтитров в LLM, которая помечает мусор/паразиты маркером [DELETE].
"""

import httpx

from utils.logger import get_logger
from utils.srt_parser import (
    SubtitleBlock, read_srt, write_srt, chunk_blocks, ms_to_timecode,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """Ты — редактор видео. Тебе дают блоки субтитров из русскоязычного видео.

Твоя задача: пометить для удаления блоки, которые содержат:
- Слова-паразиты, мычание, "ээ", "ммм", "ну", "вот", повторы
- Незаконченные фразы, оговорки, самоисправления
- Паузы и бессмысленные фрагменты
- Технический мусор (кашель, вздохи)

ВАЖНО:
- Перед текстом удаляемого блока поставь маркер [DELETE]
- НЕ МЕНЯЙ таймкоды — они должны остаться точно такими же
- НЕ МЕНЯЙ текст (кроме добавления [DELETE])
- НЕ УДАЛЯЙ блоки с осмысленным содержанием
- Сохрани нумерацию блоков без изменений
- Верни ВСЕ блоки (и помеченные, и непомеченные)

Формат вывода — стандартный SRT с маркером [DELETE] перед текстом удаляемых блоков."""


def build_srt_chunk_text(blocks):
    """Преобразование списка SubtitleBlock обратно в текст SRT для промпта ИИ."""
    lines = []
    for block in blocks:
        start_tc = ms_to_timecode(block.start_ms)
        end_tc = ms_to_timecode(block.end_ms)
        lines.append(str(block.index))
        lines.append(f"{start_tc} --> {end_tc}")
        lines.append(block.text)
        lines.append("")
    return "\n".join(lines)


def process_chunk(
    blocks,
    api_key,
    model="google/gemini-2.0-flash-001",
):
    """
    Отправка блока субтитров в OpenRouter для очистки с помощью ИИ.

    Args:
        blocks: Список объектов SubtitleBlock.
        api_key: API-ключ OpenRouter.
        model: Идентификатор модели.

    Returns:
        Текст SRT с маркерами [DELETE] от ИИ.
    """
    log = get_logger()
    srt_text = build_srt_chunk_text(blocks)

    log.info(f"Отправка {len(blocks)} блоков в ИИ ({model})...")

    response = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": srt_text},
            ],
            "temperature": 0.1,
            "max_tokens": 16000,
        },
        timeout=120.0,
    )
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]

    # Подсчёт маркеров [DELETE]
    delete_count = content.count("[DELETE]")
    log.info(f"ИИ пометил {delete_count}/{len(blocks)} блоков на удаление")

    return content


def run_ai_cleanup(srt_path, output_path, api_key, model, chunk_size=50):
    """
    Полный пайплайн очистки через ИИ: чтение SRT, разбиение на части,
    обработка каждой части, объединение результатов.

    Args:
        srt_path: Путь к входному SRT-файлу (original.srt).
        output_path: Путь для сохранения очищенного SRT (cleaned.srt).
        api_key: API-ключ OpenRouter.
        model: Идентификатор модели OpenRouter.
        chunk_size: Количество блоков субтитров на один API-запрос.

    Returns:
        Список SubtitleBlock с установленными флагами удаления.
    """
    log = get_logger()

    blocks = read_srt(srt_path)
    log.info(f"Загружено {len(blocks)} блоков субтитров из {srt_path}")

    chunks = chunk_blocks(blocks, chunk_size)
    log.info(f"Разбито на {len(chunks)} частей по {chunk_size} блоков")

    all_cleaned_text = []

    for i, chunk in enumerate(chunks, 1):
        log.info(f"Обработка части {i}/{len(chunks)}...")
        try:
            cleaned_text = process_chunk(chunk, api_key, model)
            all_cleaned_text.append(cleaned_text)
        except httpx.HTTPStatusError as e:
            log.error(f"Ошибка API в части {i}: {e.response.status_code} {e.response.text}")
            # При ошибке оставляем часть без изменений
            all_cleaned_text.append(build_srt_chunk_text(chunk))
        except Exception as e:
            log.error(f"Ошибка при обработке части {i}: {e}")
            all_cleaned_text.append(build_srt_chunk_text(chunk))

    # Объединение всего очищенного текста и парсинг
    merged_text = "\n\n".join(all_cleaned_text)

    from utils.srt_parser import parse_srt
    cleaned_blocks = parse_srt(merged_text)

    # Подсчёт удалений
    deleted = sum(1 for b in cleaned_blocks if b.deleted)
    log.info(f"Очистка ИИ завершена: {deleted}/{len(cleaned_blocks)} блоков помечено на удаление")

    # Сохранение очищенного SRT
    write_srt(cleaned_blocks, output_path)
    log.info(f"Очищенные субтитры сохранены в: {output_path}")

    return cleaned_blocks
