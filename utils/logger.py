"""
Утилита логирования — пишет в файл и в консоль.
Также поддерживает колбэк для отображения логов в интерфейсе в реальном времени.
"""

import logging
import os
import sys
from datetime import datetime


_ui_callback = None


def set_ui_callback(callback):
    """Установить колбэк-функцию(message: str) для отображения логов в интерфейсе."""
    global _ui_callback
    _ui_callback = callback


class UIHandler(logging.Handler):
    """Пользовательский обработчик, который перенаправляет сообщения логов в интерфейс."""

    def emit(self, record):
        if _ui_callback:
            try:
                msg = self.format(record)
                _ui_callback(msg)
            except Exception:
                pass


def setup_logger(working_dir="", name="autoeditor"):
    """Создать и настроить логгер плагина."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Обработчик консоли
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # Обработчик файла (если указана рабочая директория)
    if working_dir and os.path.isdir(working_dir):
        log_file = os.path.join(
            working_dir,
            f"autoeditor_{datetime.now():%Y%m%d_%H%M%S}.log",
        )
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    # Обработчик интерфейса
    ui_handler = UIHandler()
    ui_handler.setLevel(logging.INFO)
    ui_handler.setFormatter(fmt)
    logger.addHandler(ui_handler)

    return logger


def get_logger():
    """Получить существующий логгер плагина."""
    return logging.getLogger("autoeditor")
