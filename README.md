# AutoEditor — автомонтаж видео для DaVinci Resolve

Плагин для DaVinci Resolve Studio, который автоматизирует полный цикл видеомонтажа за 10 шагов — от импорта медиа до финальных титров.

## Возможности

| Шаг | Функция | Описание |
|-----|---------|----------|
| 1 | Импорт медиа | Загрузка видео и скринкаста в Media Pool с тегированием |
| 2 | Синхронизация аудио | Автосинхронизация внешнего звука по форме волны |
| 3 | Удаление тишины | Детекция пауз через ffmpeg/pydub и вырезка из таймлайна |
| 4 | Генерация субтитров | Создание SRT через Resolve Speech-to-Text (Studio) |
| 5 | Очистка ИИ | Удаление слов-паразитов и оговорок через OpenRouter API |
| 6 | Нарезка фрагментов | Пересборка таймлайна из «чистых» сегментов |
| 7 | Мультикамера | Автопереключение между камерами (V1/V2) |
| 8 | Динамический зум | Случайные зум-уровни (1.0–1.3×) для визуального разнообразия |
| 9 | Видеопереходы | Наложение переходов на V3 в точках склейки |
| 10 | Титульные карточки | Генерация титров через ffmpeg drawtext, размещение на V4 |

## Требования

- **DaVinci Resolve Studio 18+** (нужен Scripting API)
- **Python 3.10+**
- **ffmpeg** (в PATH)
- **API-ключ OpenRouter** (для шагов 5 и 10)

## Установка

### macOS

```bash
brew install python@3.10 ffmpeg

SCRIPTS=~/Library/Application\ Support/Blackmagic\ Design/DaVinci\ Resolve/Fusion/Scripts/Utility
unzip davinci-autoeditor-master.zip -d "$SCRIPTS"
mv "$SCRIPTS/davinci-autoeditor-master" "$SCRIPTS/AutoEditor"

pip3 install pydub httpx
```

### Windows

1. Установите [Python 3.10+](https://python.org) (отметьте «Add Python to PATH»)
2. Установите ffmpeg: `winget install ffmpeg`
3. Распакуйте архив в `%APPDATA%\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\AutoEditor`
4. `pip install pydub httpx`

### Linux

```bash
sudo apt update && sudo apt install python3 python3-pip ffmpeg

SCRIPTS=~/.local/share/DaVinci\ Resolve/Fusion/Scripts/Utility
unzip davinci-autoeditor-master.zip -d "$SCRIPTS"
mv "$SCRIPTS/davinci-autoeditor-master" "$SCRIPTS/AutoEditor"

pip3 install pydub httpx
```

## Запуск

В DaVinci Resolve: **Workspace → Scripts → AutoEditor → main**

API-ключ OpenRouter указывается в настройках плагина.

## Два варианта: Python и Lua

| | Python (main.py) | Lua (main.lua) |
|---|---|---|
| Зависимости | pydub, httpx | curl, ffmpeg (без pip) |
| Структура | 12 модулей + UI | Единый файл 1800 строк |
| Запуск | `main` в меню Scripts | `main` в меню Scripts |

Lua-версия полностью автономна — не требует установки Python-пакетов. Для AI-очистки используется `curl`, для анализа тишины — `ffmpeg silencedetect`.

## Структура проекта

```
├── main.lua             # Lua-версия (всё-в-одном файле)
├── main.py              # Python точка входа
├── config.py            # Конфигурация (JSON-персистенция)
├── core/                # 10 модулей автомонтажа (Python)
│   ├── media_loader.py
│   ├── audio_sync.py
│   ├── silence_remover.py
│   ├── subtitle_manager.py
│   ├── ai_processor.py
│   ├── fragment_cutter.py
│   ├── multicam.py
│   ├── zoom_animator.py
│   ├── transition_overlay.py
│   ├── title_cards.py
│   └── resolve_api.py
├── ui/main_window.py    # Интерфейс (UIManager/Qt)
├── utils/               # Утилиты (SRT, таймкоды, логгер)
├── assets/              # Стили титров, переходы
└── tests/               # Юнит-тесты
```

## Тесты

```bash
python -m pytest tests/
```

## Лицензия

MIT
