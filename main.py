"""
AutoEditor — плагин для DaVinci Resolve
Точка входа: запуск из меню Scripts или Консоли Resolve.

Использование:
    Workspace > Scripts > davinci-autoeditor > main.py
    ИЛИ
    В консоли: exec(open('/path/to/davinci-autoeditor/main.py').read())
"""

import sys
import os

# Добавляем директорию плагина в путь Python
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)


def main():
    """Запуск плагина AutoEditor."""
    from core.resolve_api import get_resolve

    resolve = get_resolve()
    fusion = resolve.Fusion()

    from ui.main_window import AutoEditorWindow
    window = AutoEditorWindow(fusion)
    window.show()


if __name__ == "__main__":
    main()
