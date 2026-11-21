"""Utilidades de formato y parseo de tiempos."""

from __future__ import annotations


def fmt_time(seconds: float) -> str:
    """Convierte segundos a 'HH:MM:SS.mmm' (para edición en la tabla)."""
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def parse_time(text: str) -> float:
    """Convierte 'HH:MM:SS.mmm' (o 'MM:SS.mmm', con coma o punto) a segundos.

    Lanza ValueError si el formato no es válido.
    """
    text = text.strip().replace(",", ".")
    parts = text.split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", parts[0], parts[1]
    else:
        raise ValueError(f"Formato de tiempo no válido: {text!r}")

    try:
        hours = int(h)
        minutes = int(m)
        seconds = float(s)
    except ValueError as exc:
        raise ValueError(f"Formato de tiempo no válido: {text!r}") from exc

    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"Minutos/segundos fuera de rango: {text!r}")

    return hours * 3600 + minutes * 60 + seconds
