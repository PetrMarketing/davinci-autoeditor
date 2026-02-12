"""
Управление конфигурацией с сохранением в JSON.
Хранит все настройки плагина в JSON-файле рядом со скриптом.
"""

import json
import os

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(CONFIG_DIR, "autoeditor_config.json")

DEFAULTS = {
    # Пути к файлам
    "main_video_path": "",
    "screencast_path": "",
    "working_dir": "",
    "transition_video_path": "",
    "title_background_path": "",
    "title_style": "default",

    # OpenRouter AI
    "openrouter_api_key": "",
    "openrouter_model": "google/gemini-2.0-flash-001",
    "ai_chunk_size": 50,  # блоков субтитров за один запрос

    # Детекция тишины
    "silence_threshold_db": -40,
    "silence_min_duration_ms": 500,

    # Зум
    "zoom_min": 1.0,
    "zoom_max": 1.3,

    # Интервалы переключения мультикам (секунды)
    "multicam_min_interval": 5,
    "multicam_max_interval": 15,

    # Таймлайн
    "timeline_name": "AutoEditor_Final",
    "fps": 25.0,

    # Субтитры
    "subtitle_language": "Russian",

    # Статусы шагов (pending / running / done / error)
    "step_statuses": {
        "1_import": "pending",
        "2_sync": "pending",
        "3_silence": "pending",
        "4_subtitles": "pending",
        "5_ai_clean": "pending",
        "6_cut": "pending",
        "7_multicam": "pending",
        "8_zoom": "pending",
        "9_transitions": "pending",
        "10_titles": "pending",
    },
}


class Config:
    """Конфигурация плагина с сохранением в JSON."""

    def __init__(self):
        self._data = {}
        self.load()

    def load(self):
        """Загрузить конфиг из JSON-файла, объединяя с умолчаниями."""
        import copy
        self._data = copy.deepcopy(DEFAULTS)
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        """Сохранить текущий конфиг в JSON-файл."""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"[Config] Ошибка сохранения: {e}")

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def set_step_status(self, step_key, status):
        """Обновить статус конкретного шага."""
        statuses = self._data.get("step_statuses", {})
        statuses[step_key] = status
        self._data["step_statuses"] = statuses
        self.save()

    def get_step_status(self, step_key):
        return self._data.get("step_statuses", {}).get(step_key, "pending")

    def reset_steps(self):
        """Сбросить все статусы шагов на pending."""
        import copy
        self._data["step_statuses"] = copy.deepcopy(DEFAULTS["step_statuses"])
        self.save()

    @property
    def working_dir(self):
        return self._data.get("working_dir", "")

    def working_path(self, filename):
        """Вернуть полный путь к файлу в рабочей директории."""
        return os.path.join(self.working_dir, filename)
