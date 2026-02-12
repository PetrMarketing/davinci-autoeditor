"""
Шаг 8: Динамическое масштабирование для каждого клипа.
Применяет едва заметные вариации масштабирования к клипам на V1 для визуального разнообразия.
"""

import random

from utils.logger import get_logger
from core.resolve_api import get_current_timeline


def apply_dynamic_zoom(zoom_min=1.0, zoom_max=1.3):
    """
    Применить случайные уровни масштабирования к каждому клипу на V1 текущего таймлайна.
    Создаёт визуальное разнообразие за счёт плавного приближения различных клипов.

    Аргументы:
        zoom_min: Минимальный коэффициент масштабирования (1.0 = без масштабирования).
        zoom_max: Максимальный коэффициент масштабирования (1.3 = приближение на 30%).

    Возвращает:
        Количество клипов, к которым применено масштабирование.
    """
    log = get_logger()
    timeline = get_current_timeline()

    if not timeline:
        raise RuntimeError("Нет активного таймлайна для анимации масштабирования")

    items = timeline.GetItemListInTrack("video", 1)
    if not items:
        log.warning("Клипы на V1 не найдены")
        return 0

    log.info(f"Применение динамического масштабирования к {len(items)} клипам на V1...")
    log.info(f"Диапазон масштабирования: {zoom_min:.2f}x — {zoom_max:.2f}x")

    count = 0
    for i, item in enumerate(items):
        # Генерируем случайный уровень масштабирования для этого клипа
        zoom = round(random.uniform(zoom_min, zoom_max), 3)

        # Применяем равномерное масштабирование (X и Y одинаковые для сохранения пропорций)
        success_x = item.SetProperty("ZoomX", zoom)
        success_y = item.SetProperty("ZoomY", zoom)

        if success_x and success_y:
            count += 1
            if zoom != 1.0:
                log.debug(f"  Клип {i + 1}: масштаб {zoom:.3f}x")
        else:
            # Запасной вариант: пробуем через свойства Инспектора
            try:
                item.SetProperty("Pan", 0)
                item.SetProperty("Tilt", 0)
                item.SetProperty("ZoomX", zoom)
                item.SetProperty("ZoomY", zoom)
                count += 1
            except Exception as e:
                log.warning(f"  Клип {i + 1}: не удалось установить масштаб — {e}")

    log.info(f"Масштабирование применено к {count}/{len(items)} клипам")
    return count


def apply_zoom_to_clip(item, zoom_x, zoom_y):
    """Применить заданные значения масштабирования к отдельному элементу таймлайна."""
    item.SetProperty("ZoomX", zoom_x)
    item.SetProperty("ZoomY", zoom_y)
