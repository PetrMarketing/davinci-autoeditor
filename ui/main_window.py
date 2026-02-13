"""
Главное окно интерфейса плагина AutoEditor.
Использует встроенный в DaVinci Resolve UIManager (на базе Qt).
"""

import os
import threading
import traceback

from config import Config
from utils.logger import get_logger, set_ui_callback, setup_logger


# Определения шагов: (ключ, название, имя_функции_запуска)
STEPS = [
    ("1_import",      "1. Импорт медиа",           "run_step_1"),
    ("2_sync",        "2. Синхронизация аудио",     "run_step_2"),
    ("3_silence",     "3. Обнаружение тишины",      "run_step_3"),
    ("4_subtitles",   "4. Генерация субтитров",     "run_step_4"),
    ("5_ai_clean",    "5. Очистка ИИ",              "run_step_5"),
    ("6_cut",         "6. Нарезка фрагментов",      "run_step_6"),
    ("7_multicam",    "7. Мультикамера",             "run_step_7"),
    ("8_zoom",        "8. Динамический зум",         "run_step_8"),
    ("9_transitions", "9. Переходы",                "run_step_9"),
    ("10_titles",     "10. Титульные карточки",      "run_step_10"),
]

STATUS_COLORS = {
    "pending": "#888888",
    "running": "#FFB800",
    "done":    "#00CC66",
    "error":   "#FF4444",
}


class AutoEditorWindow:
    """Главное окно плагина, построенное с помощью Resolve UIManager."""

    def __init__(self, fusion):
        self.fusion = fusion
        self.ui = fusion.UIManager
        self.disp = self.ui.UIDispatcher(self.ui)
        self.config = Config()
        self._running = False

        self._build_ui()
        self._load_config_to_ui()
        self._connect_events()

    def _build_ui(self):
        """Построение макета интерфейса."""
        ui = self.ui

        # --- Блок выбора файлов ---
        file_group = ui.VGroup({"ID": "FileGroup"}, [
            ui.Label({"Text": "AutoEditor — DaVinci Resolve", "Weight": 0,
                       "Font": ui.Font({"Family": "Arial", "PixelSize": 18})}),
            ui.HGroup([
                ui.Label({"Text": "Основное видео:", "Weight": 0, "MinimumSize": [140, 0]}),
                ui.LineEdit({"ID": "MainVideoPath", "PlaceholderText": "Путь к основному видео..."}),
                ui.Button({"ID": "BrowseMainVideo", "Text": "...", "MaximumSize": [30, 24]}),
            ]),
            ui.HGroup([
                ui.Label({"Text": "Скринкаст:", "Weight": 0, "MinimumSize": [140, 0]}),
                ui.LineEdit({"ID": "ScreencastPath", "PlaceholderText": "Путь к скринкасту (необязательно)..."}),
                ui.Button({"ID": "BrowseScreencast", "Text": "...", "MaximumSize": [30, 24]}),
            ]),
            ui.HGroup([
                ui.Label({"Text": "Рабочая папка:", "Weight": 0, "MinimumSize": [140, 0]}),
                ui.LineEdit({"ID": "WorkingDir", "PlaceholderText": "Директория для выходных файлов..."}),
                ui.Button({"ID": "BrowseWorkingDir", "Text": "...", "MaximumSize": [30, 24]}),
            ]),
        ])

        # --- Блок ресурсов ---
        assets_group = ui.VGroup({"ID": "AssetsGroup"}, [
            ui.Label({"Text": "Ресурсы", "Weight": 0,
                       "Font": ui.Font({"Family": "Arial", "PixelSize": 14})}),
            ui.HGroup([
                ui.Label({"Text": "Переход:", "Weight": 0, "MinimumSize": [140, 0]}),
                ui.LineEdit({"ID": "TransitionPath", "PlaceholderText": "Видео перехода (.mov/.mp4)..."}),
                ui.Button({"ID": "BrowseTransition", "Text": "...", "MaximumSize": [30, 24]}),
            ]),
            ui.HGroup([
                ui.Label({"Text": "Фон титров:", "Weight": 0, "MinimumSize": [140, 0]}),
                ui.LineEdit({"ID": "TitleBgPath", "PlaceholderText": "Фон для титров (необязательно)..."}),
                ui.Button({"ID": "BrowseTitleBg", "Text": "...", "MaximumSize": [30, 24]}),
            ]),
            ui.HGroup([
                ui.Label({"Text": "Стиль титров:", "Weight": 0, "MinimumSize": [140, 0]}),
                ui.ComboBox({"ID": "TitleStyle"}),
            ]),
        ])

        # --- Блок настроек ---
        settings_group = ui.VGroup({"ID": "SettingsGroup"}, [
            ui.Label({"Text": "Настройки", "Weight": 0,
                       "Font": ui.Font({"Family": "Arial", "PixelSize": 14})}),
            ui.HGroup([
                ui.CheckBox({"ID": "SilenceManual", "Text": "Порог тишины вручную", "Weight": 0}),
            ]),
            ui.HGroup({"ID": "SilenceRow"}, [
                ui.Label({"Text": "Порог дБ:", "Weight": 0, "MinimumSize": [140, 0]}),
                ui.SpinBox({"ID": "SilenceDb", "Minimum": -80, "Maximum": 0, "Value": -40}),
                ui.Label({"Text": "Мин. мс:", "Weight": 0}),
                ui.SpinBox({"ID": "SilenceMs", "Minimum": 100, "Maximum": 5000,
                            "Value": 500, "SingleStep": 100}),
            ]),
            ui.HGroup([
                ui.Label({"Text": "Масштаб:", "Weight": 0, "MinimumSize": [140, 0]}),
                ui.DoubleSpinBox({"ID": "ZoomMin", "Minimum": 1.0, "Maximum": 2.0,
                                  "Value": 1.0, "SingleStep": 0.05}),
                ui.Label({"Text": "—", "Weight": 0}),
                ui.DoubleSpinBox({"ID": "ZoomMax", "Minimum": 1.0, "Maximum": 2.0,
                                  "Value": 1.3, "SingleStep": 0.05}),
            ]),
            ui.HGroup([
                ui.CheckBox({"ID": "SwitchManual", "Text": "Переключение вручную", "Weight": 0}),
            ]),
            ui.HGroup({"ID": "SwitchRow"}, [
                ui.Label({"Text": "Переключ. сек:", "Weight": 0, "MinimumSize": [140, 0]}),
                ui.SpinBox({"ID": "SwitchMin", "Minimum": 1, "Maximum": 60, "Value": 5}),
                ui.Label({"Text": "—", "Weight": 0}),
                ui.SpinBox({"ID": "SwitchMax", "Minimum": 1, "Maximum": 120, "Value": 15}),
            ]),
        ])

        # --- Панель шагов ---
        step_rows = []
        for step_key, step_label, _ in STEPS:
            step_rows.append(
                ui.HGroup([
                    ui.Label({"ID": f"Status_{step_key}", "Text": "\u25cf", "Weight": 0,
                              "MinimumSize": [20, 0],
                              "StyleSheet": f"color: {STATUS_COLORS['pending']}; font-size: 16px;"}),
                    ui.Button({"ID": f"Btn_{step_key}", "Text": step_label,
                               "MinimumSize": [200, 28]}),
                ])
            )

        steps_group = ui.VGroup({"ID": "StepsGroup"}, [
            ui.Label({"Text": "Шаги", "Weight": 0,
                       "Font": ui.Font({"Family": "Arial", "PixelSize": 14})}),
            *step_rows,
            ui.HGroup([
                ui.Button({"ID": "RunAll", "Text": "Запустить все",
                            "MinimumSize": [200, 32],
                            "StyleSheet": "background-color: #2d5aa0; color: white;"}),
                ui.Button({"ID": "ResetSteps", "Text": "Сброс",
                            "MaximumSize": [80, 32]}),
            ]),
        ])

        # --- Область логов ---
        log_group = ui.VGroup({"ID": "LogGroup"}, [
            ui.Label({"Text": "Журнал", "Weight": 0,
                       "Font": ui.Font({"Family": "Arial", "PixelSize": 14})}),
            ui.TextEdit({"ID": "LogArea", "ReadOnly": True,
                         "Font": ui.Font({"Family": "Courier", "PixelSize": 11}),
                         "MinimumSize": [0, 200]}),
            ui.Button({"ID": "ClearLog", "Text": "Очистить",
                        "MaximumSize": [100, 24]}),
        ])

        # --- Главное окно ---
        self.win = self.disp.AddWindow(
            {
                "ID": "AutoEditorWin",
                "WindowTitle": "AutoEditor",
                "Geometry": [200, 100, 700, 900],
            },
            ui.VGroup([
                file_group,
                assets_group,
                settings_group,
                ui.HGroup([steps_group, log_group]),
            ]),
        )

        self.items = self.win.GetItems()

        # Заполняем комбобокс стилей титров
        self._load_title_styles()

    def _load_title_styles(self):
        """Загрузить доступные стили титров в выпадающий список."""
        combo = self.items.get("TitleStyle")
        if not combo:
            return
        combo.AddItem("default")
        styles_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets", "titles", "styles.json",
        )
        if os.path.exists(styles_file):
            try:
                import json
                with open(styles_file, "r", encoding="utf-8") as f:
                    styles = json.load(f)
                for name in styles:
                    if name != "default":
                        combo.AddItem(name)
            except Exception:
                pass

    def _load_config_to_ui(self):
        """Заполнить поля интерфейса из сохранённого конфига."""
        c = self.config
        items = self.items
        items["MainVideoPath"].Text = c.get("main_video_path", "")
        items["ScreencastPath"].Text = c.get("screencast_path", "")
        items["WorkingDir"].Text = c.get("working_dir", "")
        items["TransitionPath"].Text = c.get("transition_video_path", "")
        items["TitleBgPath"].Text = c.get("title_background_path", "")
        items["SilenceManual"].Checked = c.get("silence_manual", False)
        items["SilenceDb"].Value = c.get("silence_threshold_db", -40)
        items["SilenceMs"].Value = c.get("silence_min_duration_ms", 500)
        items["SilenceRow"].Hidden = not c.get("silence_manual", False)
        items["ZoomMin"].Value = c.get("zoom_min", 1.0)
        items["ZoomMax"].Value = c.get("zoom_max", 1.3)
        items["SwitchManual"].Checked = c.get("multicam_manual", False)
        items["SwitchMin"].Value = c.get("multicam_min_interval", 5)
        items["SwitchMax"].Value = c.get("multicam_max_interval", 15)
        items["SwitchRow"].Hidden = not c.get("multicam_manual", False)

        # Восстановление статусов шагов
        for step_key, _, _ in STEPS:
            status = c.get_step_status(step_key)
            self._update_step_status_ui(step_key, status)

    def _save_config_from_ui(self):
        """Сохранить значения полей интерфейса в конфиг."""
        c = self.config
        items = self.items
        c.set("main_video_path", items["MainVideoPath"].Text)
        c.set("screencast_path", items["ScreencastPath"].Text)
        c.set("working_dir", items["WorkingDir"].Text)
        c.set("transition_video_path", items["TransitionPath"].Text)
        c.set("title_background_path", items["TitleBgPath"].Text)
        c.set("silence_manual", items["SilenceManual"].Checked)
        c.set("silence_threshold_db", items["SilenceDb"].Value)
        c.set("silence_min_duration_ms", items["SilenceMs"].Value)
        c.set("zoom_min", items["ZoomMin"].Value)
        c.set("zoom_max", items["ZoomMax"].Value)
        c.set("multicam_manual", items["SwitchManual"].Checked)
        c.set("multicam_min_interval", items["SwitchMin"].Value)
        c.set("multicam_max_interval", items["SwitchMax"].Value)
        c.save()

    def _connect_events(self):
        """Подключение кнопок интерфейса к обработчикам."""
        self.win.On.AutoEditorWin.Close = self._on_close
        self.win.On.ClearLog.Clicked = self._on_clear_log
        self.win.On.ResetSteps.Clicked = self._on_reset_steps
        self.win.On.RunAll.Clicked = self._on_run_all

        # Чекбоксы ручного режима
        self.win.On.SilenceManual.Clicked = self._on_silence_manual_toggle
        self.win.On.SwitchManual.Clicked = self._on_switch_manual_toggle

        # Кнопки обзора файлов
        self.win.On.BrowseMainVideo.Clicked = lambda ev: self._browse("MainVideoPath")
        self.win.On.BrowseScreencast.Clicked = lambda ev: self._browse("ScreencastPath")
        self.win.On.BrowseWorkingDir.Clicked = lambda ev: self._browse("WorkingDir", folder=True)
        self.win.On.BrowseTransition.Clicked = lambda ev: self._browse("TransitionPath")
        self.win.On.BrowseTitleBg.Clicked = lambda ev: self._browse("TitleBgPath")

        # Кнопки отдельных шагов
        for step_key, _, runner_name in STEPS:
            btn_id = f"Btn_{step_key}"
            # Захватываем step_key в замыкании
            self.win.On[btn_id].Clicked = (
                lambda ev, sk=step_key: self._on_step_click(sk)
            )

    def _browse(self, field_id, folder=False):
        """Открыть диалог выбора файла/папки."""
        if folder:
            path = self.fusion.RequestDir()
        else:
            path = self.fusion.RequestFile()
        if path:
            self.items[field_id].Text = str(path)

    def _update_step_status_ui(self, step_key, status):
        """Обновить визуальный индикатор статуса шага."""
        label_id = f"Status_{step_key}"
        label = self.items.get(label_id)
        if label:
            color = STATUS_COLORS.get(status, STATUS_COLORS["pending"])
            label.StyleSheet = f"color: {color}; font-size: 16px;"

    def _log(self, message):
        """Добавить сообщение в область логов."""
        log_area = self.items.get("LogArea")
        if log_area:
            log_area.Append(message + "\n")

    def _on_silence_manual_toggle(self, ev):
        self.items["SilenceRow"].Hidden = not self.items["SilenceManual"].Checked

    def _on_switch_manual_toggle(self, ev):
        self.items["SwitchRow"].Hidden = not self.items["SwitchManual"].Checked

    def _on_close(self, ev):
        self._save_config_from_ui()
        self.disp.ExitLoop()

    def _on_clear_log(self, ev):
        self.items["LogArea"].Clear()

    def _on_reset_steps(self, ev):
        self.config.reset_steps()
        for step_key, _, _ in STEPS:
            self._update_step_status_ui(step_key, "pending")
        self._log("Все шаги сброшены в состояние ожидания.")

    def _on_step_click(self, step_key):
        """Запустить отдельный шаг."""
        if self._running:
            self._log("Другой шаг уже выполняется. Подождите.")
            return
        self._save_config_from_ui()
        self._run_step(step_key)

    def _on_run_all(self, ev):
        """Запустить все шаги последовательно в фоновом потоке."""
        if self._running:
            self._log("Шаги уже выполняются. Подождите.")
            return
        self._save_config_from_ui()

        def run_all_thread():
            for step_key, step_label, _ in STEPS:
                if not self._running:
                    break
                status = self.config.get_step_status(step_key)
                if status == "done":
                    self._log(f"Пропуск: {step_label} (уже выполнен)")
                    continue
                self._run_step(step_key)
                if self.config.get_step_status(step_key) == "error":
                    self._log(f"Остановка: {step_label} завершился с ошибкой")
                    break
            self._running = False

        self._running = True
        thread = threading.Thread(target=run_all_thread, daemon=True)
        thread.start()

    def _run_step(self, step_key):
        """Выполнить конкретный шаг и обновить статус."""
        self._running = True
        self.config.set_step_status(step_key, "running")
        self._update_step_status_ui(step_key, "running")

        log = get_logger()
        step_label = next(
            (label for key, label, _ in STEPS if key == step_key), step_key
        )
        log.info(f"=== Запуск: {step_label} ===")

        try:
            runner = getattr(self, f"_runner_{step_key}", None)
            if runner is None:
                raise NotImplementedError(f"Нет обработчика для шага: {step_key}")
            runner()
            self.config.set_step_status(step_key, "done")
            self._update_step_status_ui(step_key, "done")
            log.info(f"=== Завершён: {step_label} ===")
        except Exception as e:
            self.config.set_step_status(step_key, "error")
            self._update_step_status_ui(step_key, "error")
            log.error(f"=== Ошибка: {step_label} — {e} ===")
            log.debug(traceback.format_exc())
        finally:
            self._running = False

    # --- Обработчики шагов ---

    def _runner_1_import(self):
        from core.media_loader import import_media
        c = self.config
        import_media(c.get("main_video_path"), c.get("screencast_path"))

    def _runner_2_sync(self):
        from core.media_loader import find_tagged_clips
        from core.audio_sync import auto_sync_audio
        clips = find_tagged_clips()
        auto_sync_audio(clips, self.config)

    def _runner_3_silence(self):
        from core.silence_remover import detect_silence, auto_detect_threshold
        c = self.config
        video_path = c.get("main_video_path")
        if c.get("silence_manual", False):
            threshold = c.get("silence_threshold_db", -40)
        else:
            threshold = auto_detect_threshold(video_path)
        detect_silence(
            video_path,
            threshold_db=threshold,
            min_duration_ms=c.get("silence_min_duration_ms", 500),
            working_dir=c.get("working_dir"),
        )

    def _runner_4_subtitles(self):
        from core.subtitle_manager import generate_subtitles, export_subtitles
        c = self.config
        generate_subtitles(c.get("subtitle_language", "Russian"))
        export_subtitles(c.get("working_dir"), "original.srt")

    def _runner_5_ai_clean(self):
        from core.ai_processor import run_ai_cleanup
        c = self.config
        run_ai_cleanup(
            srt_path=c.working_path("original.srt"),
            output_path=c.working_path("cleaned.srt"),
            api_key=c.get("openrouter_api_key"),
            model=c.get("openrouter_model"),
            chunk_size=c.get("ai_chunk_size", 50),
        )

    def _runner_6_cut(self):
        from core.media_loader import find_tagged_clips
        from core.fragment_cutter import compute_keep_segments, rebuild_timeline
        from core.resolve_api import get_clip_duration_ms, get_fps

        c = self.config
        clips = find_tagged_clips()
        main_clip = clips.get("main")
        if not main_clip:
            raise RuntimeError("Основной клип не найден в медиапуле")

        total_ms = get_clip_duration_ms(main_clip)
        fps = get_fps()
        keep = compute_keep_segments(c.get("working_dir"), total_ms, fps)
        rebuild_timeline(
            main_clip, keep, c.get("timeline_name", "AutoEditor_Final"), fps,
            screencast_clip=clips.get("screencast"),
            audio_offset_ms=c.get("audio_offset_ms", 0),
        )

    def _runner_7_multicam(self):
        from core.media_loader import find_tagged_clips
        from core.multicam import distribute_multicam, auto_switch_intervals
        from core.fragment_cutter import load_keep_segments
        from core.resolve_api import get_fps

        c = self.config
        clips = find_tagged_clips()
        sc = clips.get("screencast")
        if not sc:
            get_logger().info("Скринкаст отсутствует — пропускаем мультикамеру")
            return
        keep = load_keep_segments(c.get("working_dir"))
        if c.get("multicam_manual", False):
            min_iv = c.get("multicam_min_interval", 5)
            max_iv = c.get("multicam_max_interval", 15)
        else:
            min_iv, max_iv = auto_switch_intervals(keep)
        distribute_multicam(
            sc, keep,
            min_interval_sec=min_iv,
            max_interval_sec=max_iv,
            fps=get_fps(),
            audio_offset_ms=c.get("audio_offset_ms", 0),
        )

    def _runner_8_zoom(self):
        from core.zoom_animator import apply_dynamic_zoom
        c = self.config
        apply_dynamic_zoom(c.get("zoom_min", 1.0), c.get("zoom_max", 1.3))

    def _runner_9_transitions(self):
        from core.transition_overlay import import_transition_video, apply_transitions
        from core.resolve_api import get_fps
        c = self.config
        tr_path = c.get("transition_video_path")
        if not tr_path:
            get_logger().info("Видео перехода не указано — пропускаем")
            return
        tr_clip = import_transition_video(tr_path)
        apply_transitions(tr_clip, get_fps())

    def _runner_10_titles(self):
        from core.title_cards import create_chapter_titles, detect_chapters_from_subtitles
        from core.resolve_api import get_fps
        c = self.config
        wd = c.get("working_dir")

        # Автоматическое определение глав из очищенных субтитров
        cleaned_srt = c.working_path("cleaned.srt")
        original_srt = c.working_path("original.srt")
        srt_to_use = cleaned_srt if os.path.exists(cleaned_srt) else original_srt

        chapters = []
        if os.path.exists(srt_to_use):
            chapters = detect_chapters_from_subtitles(srt_to_use)

        create_chapter_titles(
            chapters,
            wd,
            background_path=c.get("title_background_path", ""),
            style_name=c.get("title_style", "default"),
            fps=get_fps(),
        )

    def show(self):
        """Отобразить окно и войти в цикл обработки событий."""
        # Настройка логгера с колбэком для интерфейса
        setup_logger(self.config.get("working_dir", ""))
        set_ui_callback(self._log)

        self.win.Show()
        self.disp.RunLoop()
        self.win.Hide()
