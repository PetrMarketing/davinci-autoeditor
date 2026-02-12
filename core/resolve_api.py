"""
Обёртка над API DaVinci Resolve.
Обеспечивает безопасный доступ к объектам Resolve и типовые операции.
"""

from utils.logger import get_logger

_resolve = None
_project = None


def get_resolve():
    """Получить объект Resolve Scripting. Должен вызываться изнутри Resolve."""
    global _resolve
    if _resolve is None:
        try:
            import DaVinciResolveScript as dvr
            _resolve = dvr.scriptapp("Resolve")
        except ImportError:
            # Запасной вариант: Resolve внедряет 'resolve' в глобальную область видимости
            # при запуске из Workspace > Console
            import builtins
            _resolve = getattr(builtins, "resolve", None)
        if _resolve is None:
            raise RuntimeError(
                "Не удалось подключиться к DaVinci Resolve. "
                "Запустите этот скрипт из Resolve (Workspace > Scripts)."
            )
    return _resolve


def get_project_manager():
    return get_resolve().GetProjectManager()


def get_current_project():
    global _project
    if _project is None:
        _project = get_project_manager().GetCurrentProject()
    return _project


def get_media_pool():
    return get_current_project().GetMediaPool()


def get_current_timeline():
    return get_current_project().GetCurrentTimeline()


def get_fps():
    """Получить FPS текущего таймлайна в виде float."""
    tl = get_current_timeline()
    if tl:
        setting = tl.GetSetting("timelineFrameRate")
        try:
            return float(setting)
        except (ValueError, TypeError):
            pass
    return 25.0


def create_timeline(name):
    """Создать новый пустой таймлайн и установить его текущим."""
    log = get_logger()
    mp = get_media_pool()
    tl = mp.CreateEmptyTimeline(name)
    if tl:
        get_current_project().SetCurrentTimeline(tl)
        log.info(f"Таймлайн создан: {name}")
    else:
        log.error(f"Не удалось создать таймлайн: {name}")
    return tl


def get_timeline_by_name(name):
    """Найти таймлайн по имени в текущем проекте."""
    project = get_current_project()
    count = project.GetTimelineCount()
    for i in range(1, count + 1):
        tl = project.GetTimelineByIndex(i)
        if tl and tl.GetName() == name:
            return tl
    return None


def get_root_folder():
    """Получить корневую папку медиапула."""
    return get_media_pool().GetRootFolder()


def find_bin(name, parent=None):
    """Найти или создать бин (папку) в медиапуле."""
    mp = get_media_pool()
    if parent is None:
        parent = get_root_folder()

    for sub in parent.GetSubFolderList():
        if sub.GetName() == name:
            return sub

    mp.SetCurrentFolder(parent)
    return mp.AddSubFolder(parent, name)


def get_clip_duration_frames(clip):
    """Получить длительность клипа из медиапула в кадрах."""
    props = clip.GetClipProperty()
    # Длительность обычно в формате "HH:MM:SS:FF"
    duration_str = props.get("Duration", "")
    if not duration_str:
        return 0
    parts = duration_str.split(":")
    if len(parts) == 4:
        from utils.timecode import resolve_tc_to_frames
        fps = get_fps()
        return resolve_tc_to_frames(duration_str, fps)
    return 0


def get_clip_duration_ms(clip):
    """Получить длительность клипа из медиапула в миллисекундах."""
    frames = get_clip_duration_frames(clip)
    fps = get_fps()
    return int(round(frames / fps * 1000))
