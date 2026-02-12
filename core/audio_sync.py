"""
Шаг 2: Автоматическая синхронизация аудио между основным видео и скринкастом
с помощью анализа звуковой волны.
Использует встроенную функцию Resolve AutoSyncAudio в режиме waveform.
"""

from utils.logger import get_logger
from core.resolve_api import get_media_pool


# Константы режимов AutoSyncAudio в Resolve
SYNC_MODE_WAVEFORM = 0
SYNC_MODE_TIMECODE = 1
SYNC_MODE_IN_OUT = 2


def auto_sync_audio(clips_dict):
    """
    Синхронизировать аудио между клипами основного видео и скринкаста.

    Аргументы:
        clips_dict: dict с объектами MediaPoolItem по ключам 'main' и 'screencast'.

    Возвращает:
        Синхронизированный клип (MediaPoolItem) или None, если клип только один.
    """
    log = get_logger()

    main_clip = clips_dict.get("main")
    screencast_clip = clips_dict.get("screencast")

    if not main_clip:
        raise RuntimeError("Основной клип для синхронизации аудио не найден")

    if not screencast_clip:
        log.info("Скринкаст отсутствует — пропуск синхронизации аудио")
        return main_clip

    mp = get_media_pool()

    log.info("Запуск синхронизации аудио по звуковой волне...")
    log.info(f"  Основной: {main_clip.GetName()}")
    log.info(f"  Скринкаст: {screencast_clip.GetName()}")

    # AutoSyncAudio принимает список клипов и параметры синхронизации
    clip_list = [main_clip, screencast_clip]
    synced = mp.AutoSyncAudio(
        clip_list,
        {
            "syncMode": SYNC_MODE_WAVEFORM,
            "isActive": True,
        },
    )

    if synced:
        log.info("Синхронизация аудио завершена успешно")
        # Синхронизированный клип заменяет или связывает исходные
        if isinstance(synced, list) and len(synced) > 0:
            return synced[0]
        return synced
    else:
        log.warning(
            "AutoSyncAudio не вернул результат. "
            "Возможно, клипы требуют ручного выравнивания или аудиодорожки значительно отличаются."
        )
        return main_clip
