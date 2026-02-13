"""
Шаг 2: Автоматическая синхронизация аудио между основным видео и скринкастом.
Пробует встроенный AutoSyncAudio (если доступен в версии Resolve),
иначе — выравнивает клипы по началу с предупреждением.
"""

from utils.logger import get_logger
from core.resolve_api import get_media_pool

SYNC_MODE_WAVEFORM = 0


def auto_sync_audio(clips_dict):
    """
    Синхронизировать аудио между клипами основного видео и скринкаста.

    Аргументы:
        clips_dict: dict с объектами MediaPoolItem по ключам 'main' и 'screencast'.

    Возвращает:
        Синхронизированный клип (MediaPoolItem) или основной клип при отсутствии скринкаста.
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

    log.info("Синхронизация аудио...")
    log.info(f"  Основной: {main_clip.GetName()}")
    log.info(f"  Скринкаст: {screencast_clip.GetName()}")

    # Способ 1: пробуем AutoSyncAudio (Resolve 19+)
    if hasattr(mp, "AutoSyncAudio"):
        try:
            synced = mp.AutoSyncAudio(
                [main_clip, screencast_clip],
                {"syncMode": SYNC_MODE_WAVEFORM, "isActive": True},
            )
            if synced:
                log.info("AutoSyncAudio выполнен успешно")
                if isinstance(synced, list) and len(synced) > 0:
                    return synced[0]
                return synced
            log.warning("AutoSyncAudio не вернул результат, пробуем альтернативный метод...")
        except Exception as e:
            log.warning(f"AutoSyncAudio вызвал ошибку: {e}")

    # Способ 2: клипы будут выровнены по началу
    log.info("Автосинхронизация через API недоступна в этой версии Resolve.")
    log.info("Клипы будут синхронизированы по началу. При необходимости скорректируйте вручную на таймлайне.")

    return main_clip
