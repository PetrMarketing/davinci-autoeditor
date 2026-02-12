"""
Утилиты конвертации таймкодов, кадров и миллисекунд.
"""


def ms_to_timecode(ms, fps=25.0):
    """Конвертировать миллисекунды в SRT-таймкод формата HH:MM:SS,mmm."""
    if ms < 0:
        ms = 0
    total_seconds = ms / 1000.0
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    millis = int(ms % 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def timecode_to_ms(tc):
    """Конвертировать SRT-таймкод формата HH:MM:SS,mmm в миллисекунды."""
    tc = tc.strip()
    # Поддержка как запятой, так и точки в качестве десятичного разделителя
    tc = tc.replace(",", ".")
    parts = tc.split(":")
    if len(parts) != 3:
        raise ValueError(f"Некорректный таймкод: {tc}")
    hours = int(parts[0])
    minutes = int(parts[1])
    sec_parts = parts[2].split(".")
    seconds = int(sec_parts[0])
    millis = int(sec_parts[1]) if len(sec_parts) > 1 else 0
    return (hours * 3600 + minutes * 60 + seconds) * 1000 + millis


def ms_to_frames(ms, fps=25.0):
    """Конвертировать миллисекунды в номер кадра."""
    return int(round(ms / 1000.0 * fps))


def frames_to_ms(frames, fps=25.0):
    """Конвертировать номер кадра в миллисекунды."""
    return int(round(frames / fps * 1000))


def frames_to_resolve_tc(frames, fps=25.0):
    """Конвертировать количество кадров в таймкод формата Resolve HH:MM:SS:FF."""
    fps_int = int(round(fps))
    f = frames % fps_int
    total_seconds = frames // fps_int
    s = total_seconds % 60
    total_minutes = total_seconds // 60
    m = total_minutes % 60
    h = total_minutes // 60
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def resolve_tc_to_frames(tc, fps=25.0):
    """Конвертировать таймкод формата Resolve HH:MM:SS:FF в количество кадров."""
    parts = tc.strip().split(":")
    if len(parts) != 4:
        raise ValueError(f"Некорректный таймкод Resolve: {tc}")
    fps_int = int(round(fps))
    h, m, s, f = [int(p) for p in parts]
    return ((h * 3600 + m * 60 + s) * fps_int) + f
