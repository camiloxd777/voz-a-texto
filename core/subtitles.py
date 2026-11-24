"""Modelo de datos de subtítulos y post-procesado.

Convierte las palabras con marcas de tiempo (de la transcripción) en "cues"
(líneas de subtítulo) aplicando reglas tipo Premiere:

- máximo de caracteres por línea,
- pausa máxima dentro de una línea (para cortar en silencios),
- duración mínima y máxima por línea.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .transcriber import Word


@dataclass
class SubtitleCue:
    """Una línea de subtítulo lista para exportar."""

    index: int
    start: float
    end: float
    text: str


@dataclass
class SubtitleTrack:
    """Colección de cues con utilidades de edición."""

    cues: list[SubtitleCue] = field(default_factory=list)

    def reindex(self) -> None:
        for i, cue in enumerate(self.cues, start=1):
            cue.index = i

    def to_words(self) -> list[Word]:
        """Reconstruye una lista plana de palabras (para re-procesar con
        otros parámetros si el usuario cambia el ajuste)."""
        words: list[Word] = []
        for cue in self.cues:
            parts = cue.text.split()
            if not parts:
                continue
            n = len(parts)
            duration = max(cue.end - cue.start, 0.0)
            per = duration / n
            for j, p in enumerate(parts):
                words.append(
                    Word(
                        start=cue.start + j * per,
                        end=cue.start + (j + 1) * per,
                        text=p,
                    )
                )
        return words


def _format_cue_text(words: list[Word], max_lines: int = 1) -> str:
    texts = [w.text.strip() for w in words if w.text.strip()]
    if max_lines == 2 and len(texts) >= 2:
        # Reparte las palabras en 2 líneas (la primera con la mitad inferior,
        # p.ej. 3 palabras -> 1 y 2: "hola" / "cómo estás").
        split = len(texts) // 2
        return " ".join(texts[:split]) + "\n" + " ".join(texts[split:])
    return " ".join(texts)


def words_from_segments(segments) -> list[Word]:
    """Fallback si no hay timestamps de palabra: reparte cada segmento en palabras.

    Útil cuando Whisper no devuelve `word_timestamps`.
    """
    words: list[Word] = []
    for seg in segments:
        parts = seg.text.split()
        if not parts:
            continue
        per = max(seg.end - seg.start, 0.0) / len(parts)
        for i, p in enumerate(parts):
            words.append(
                Word(start=seg.start + i * per, end=seg.start + (i + 1) * per, text=p)
            )
    return words


def build_cues(
    words: list[Word],
    max_words: int = 3,
    max_chars: int = 18,
    max_gap: float = 0.4,
    min_duration: float = 0.3,
    max_duration: float = 4.0,
    max_lines: int = 1,
    end_padding: float = 0.03,
) -> list[SubtitleCue]:
    """Agrupa palabras en cues (frases cortas, estilo guion).

    Parámetros
    ----------
    max_words     : máximo de palabras por cue (estilo guion).
    max_chars     : tope de seguridad por si una sola palabra es muy larga.
    max_gap       : pausa (s) entre palabras que fuerza un corte de cue.
    min_duration  : duración mínima de una cue (se extiende el final).
    max_duration  : duración máxima de una cue (se corta en silencio).
    max_lines     : número de líneas en las que se reparte el texto (1 o 2).
    end_padding   : margen extra al final de cada cue (s) para evitar cortes tempranos.
    """
    if not words:
        return []

    cues: list[SubtitleCue] = []
    current: list[Word] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        cues.append(_make_cue(current, min_duration, max_lines, end_padding=end_padding))
        current = []

    for w in words:
        text = w.text.strip()
        if not text:
            continue

        # 1) Máximo de palabras por cue (estilo guion).
        if current and len(current) >= max_words:
            flush()

        # 2) Pausa antes de esta palabra -> cortar el cue.
        if current and (w.start - current[-1].end) > max_gap:
            flush()

        # 3) Duración máxima del cue.
        if current and (w.end - current[0].start) > max_duration and len(current) >= 2:
            flush()

        # 4) Tope de caracteres (seguridad ante palabras muy largas).
        if current:
            char_count = sum(len(x.text) for x in current) + len(text) + len(current)
            if char_count > max_chars:
                flush()

        current.append(w)

    flush()

    # Evitar solapamientos y sangrado al siguiente subtítulo.
    # Dejar un pequeño hueco cuando sea posible para que no "pise" la siguiente voz.
    for i in range(len(cues) - 1):
        next_start = cues[i + 1].start
        max_end = next_start - 0.02 if (next_start - cues[i].start) > 0.08 else next_start
        if cues[i].end > max_end:
            cues[i].end = max(cues[i].start + 0.05, max_end)

    track = SubtitleTrack(cues)
    track.reindex()
    return track.cues


def _make_cue(
    words: list[Word], min_duration: float, max_lines: int = 1, end_padding: float = 0.25
) -> SubtitleCue:
    start = min(w.start for w in words)
    end = max(w.end for w in words) + max(0.0, end_padding)

    # Garantizar duración mínima extendiendo el final.
    if end - start < min_duration:
        end = start + min_duration

    return SubtitleCue(
        index=0, start=start, end=end, text=_format_cue_text(words, max_lines)
    )
