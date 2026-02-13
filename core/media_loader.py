"""
Шаг 1: Импорт медиафайлов в медиапул DaVinci Resolve.
Импортирует основное видео и опциональный скринкаст, присваивая им роли через теги.
"""

import os
from utils.logger import get_logger
from core.resolve_api import get_media_pool, get_current_project, find_bin


def import_media(main_video_path, screencast_path=""):
    """
    Импортировать медиафайлы в медиапул.

    Аргументы:
        main_video_path: Путь к файлу основного видео с камеры.
        screencast_path: Необязательный путь к скринкасту/записи экрана.

    Возвращает:
        dict с ключами 'main' и опционально 'screencast', указывающими на объекты MediaPoolItem.
    """
    log = get_logger()
    mp = get_media_pool()
    result = {}

    if not main_video_path or not os.path.isfile(main_video_path):
        raise FileNotFoundError(f"Основное видео не найдено: {main_video_path}")

    # Создаём бин "AutoEditor" для организации файлов
    ae_bin = find_bin("AutoEditor")
    mp.SetCurrentFolder(ae_bin)

    # Импорт основного видео
    log.info(f"Импорт основного видео: {os.path.basename(main_video_path)}")
    clips = mp.ImportMedia([main_video_path])
    if not clips or len(clips) == 0:
        raise RuntimeError(f"Не удалось импортировать: {main_video_path}")

    main_clip = clips[0]
    main_clip.SetClipProperty("Comments", "AutoEditor:main")
    result["main"] = main_clip
    log.info(f"Основное видео импортировано: {main_clip.GetName()}")

    # Импорт скринкаста, если указан
    if screencast_path and os.path.isfile(screencast_path):
        log.info(f"Импорт скринкаста: {os.path.basename(screencast_path)}")
        sc_clips = mp.ImportMedia([screencast_path])
        if sc_clips and len(sc_clips) > 0:
            sc_clip = sc_clips[0]
            sc_clip.SetClipProperty("Comments", "AutoEditor:screencast")
            result["screencast"] = sc_clip
            log.info(f"Скринкаст импортирован: {sc_clip.GetName()}")
        else:
            log.warning(f"Не удалось импортировать скринкаст: {screencast_path}")
    elif screencast_path:
        log.warning(f"Файл скринкаста не найден: {screencast_path}")

    # Создаём таймлайн и размещаем клипы: V1=основное видео, V2=скринкаст
    from core.resolve_api import get_timeline_by_name, create_timeline
    tl_name = "AutoEditor_Timeline"

    # Проверяем, не существует ли уже такой таймлайн
    existing_tl = get_timeline_by_name(tl_name)
    if existing_tl:
        get_current_project().SetCurrentTimeline(existing_tl)
        log.info(f"Таймлайн уже существует: {tl_name} (используется существующий)")
    else:
        tl = mp.CreateTimelineFromClips(tl_name, [main_clip])
        if tl:
            get_current_project().SetCurrentTimeline(tl)
            log.info(f"Таймлайн создан: {tl_name} (основной клип на V1)")
        else:
            log.info("Пробуем альтернативный способ создания таймлайна...")
            tl = create_timeline(tl_name)
            if tl:
                appended = mp.AppendToTimeline([main_clip])
                if appended:
                    log.info(f"Таймлайн создан: {tl_name} (основной клип добавлен на V1)")
                else:
                    log.warning("Таймлайн создан, но клип не удалось добавить")
            else:
                log.warning("Не удалось создать таймлайн автоматически")

        # Добавляем скринкаст на V2 (если есть)
        if "screencast" in result and tl:
            log.info("Добавление скринкаста на V2...")
            if tl.GetTrackCount("video") < 2:
                tl.AddTrack("video")
            sc_info = {
                "mediaPoolItem": result["screencast"],
                "startFrame": 0,
                "trackIndex": 2,
                "mediaType": 1,
            }
            sc_ok = mp.AppendToTimeline([sc_info])
            if sc_ok:
                log.info("Скринкаст размещён на V2")
                tl.SetTrackEnable("audio", 2, False)
                log.info("Аудио на V2 отключено (используется аудио основного видео)")
            else:
                log.warning("Не удалось добавить скринкаст на V2")

    log.info(f"Шаг 1 завершён: импортировано клипов: {len(result)}")
    return result


def find_tagged_clips():
    """
    Найти ранее импортированные клипы AutoEditor по тегу в комментариях.

    Возвращает:
        dict с ключами 'main' и/или 'screencast'.
    """
    from core.resolve_api import get_root_folder

    result = {}
    root = get_root_folder()
    _search_folder(root, result)
    return result


def _search_folder(folder, result):
    """Рекурсивный поиск помеченных клипов в папках."""
    for clip in folder.GetClipList():
        comments = clip.GetClipProperty("Comments") or ""
        if "AutoEditor:main" in comments:
            result["main"] = clip
        elif "AutoEditor:screencast" in comments:
            result["screencast"] = clip

    for sub in folder.GetSubFolderList():
        _search_folder(sub, result)
