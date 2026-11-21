"""Exportadores de subtítulos a formato SRT y ASS."""

from __future__ import annotations

from dataclasses import dataclass

from .subtitles import SubtitleCue


def _srt_time(seconds: float) -> str:
    """Convierte segundos a 'HH:MM:SS,mmm' (formato SRT)."""
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(seconds: float) -> str:
    """Convierte segundos a 'H:MM:SS.cc' (centésimas, formato ASS)."""
    cs = int(round(seconds * 100))
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def to_srt(cues: list[SubtitleCue]) -> str:
    """Genera el contenido de un archivo .srt."""
    blocks = []
    for cue in cues:
        blocks.append(
            f"{cue.index}\n"
            f"{_srt_time(cue.start)} --> {_srt_time(cue.end)}\n"
            f"{cue.text}\n"
        )
    return "\n".join(blocks) + ("\n" if blocks else "")


@dataclass
class AssStyle:
    """Opciones de estilo para el subtítulo ASS."""

    font_name: str = "Arial"
    font_size: int = 54
    primary_color: str = "&H00FFFFFF"   # blanco (formato &HAABBGGRR)
    outline_color: str = "&H00000000"   # negro
    back_color: str = "&H80000000"      # sombra semi-transparente
    bold: int = 1
    outline: float = 2.0
    shadow: float = 1.5
    alignment: int = 2  # 2 = abajo centrado (estilo subtítulo)


def _ass_header(style: AssStyle, width: int = 1920, height: int = 1080) -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: TV.709\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{style.font_name},{style.font_size},"
        f"{style.primary_color},&H000000FF,{style.outline_color},"
        f"{style.back_color},{style.bold},0,0,0,100,100,0,0,1,"
        f"{style.outline},{style.shadow},{style.alignment},60,60,60,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )


def to_ass(cues: list[SubtitleCue], style: AssStyle | None = None) -> str:
    """Genera el contenido de un archivo .ass."""
    style = style or AssStyle()
    lines = [_ass_header(style)]
    for cue in cues:
        # '\N' es salto de línea en ASS; aquí se usa texto en una sola línea.
        text = cue.text.replace("\n", "\\N")
        lines.append(
            f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},"
            f"Default,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Exportador nativo de Vegas (Insert > Insert Subtitles from File)
# ---------------------------------------------------------------------------

def _is_drop_frame(fps: float) -> bool:
    return abs(fps - 29.97) < 0.001 or abs(fps - 59.94) < 0.001


def _nominal_fps(fps: float) -> int:
    """FPS nominal para el etiquetado de frames (29.97 -> 30, 59.94 -> 60)."""
    if abs(fps - 29.97) < 0.001:
        return 30
    if abs(fps - 59.94) < 0.001:
        return 60
    return int(round(fps))


def _drop_frame_adjust(frames: int, nominal: int) -> int:
    """Ajuste SMPTE drop-frame: añade los frames 'saltados' al conteo real."""
    drop_frames = 2 if nominal == 30 else 4  # 29.97 -> 2, 59.94 -> 4
    frames_per_10min = nominal * 60 * 10
    frames_per_minute = nominal * 60 - drop_frames

    d = frames // frames_per_10min
    m = frames % frames_per_10min
    if m > drop_frames:
        frames += drop_frames * 9 * d + drop_frames * ((m - drop_frames) // frames_per_minute)
    else:
        frames += drop_frames * 9 * d
    return frames


def seconds_to_timecode(seconds: float, fps: float = 29.97) -> str:
    """Convierte segundos a timecode 'HH:MM:SS;FF' (o ':' si no es drop-frame).

    Sigue el formato que espera el importador nativo de Vegas 2026
    (SMPTE Drop 29.97 por defecto).
    """
    drop_frame = _is_drop_frame(fps)
    nominal = _nominal_fps(fps)

    frames = int(round(seconds * fps))
    if drop_frame:
        frames = _drop_frame_adjust(frames, nominal)

    ff = frames % nominal
    total_sec = frames // nominal
    ss = total_sec % 60
    mm = (total_sec // 60) % 60
    hh = total_sec // 3600

    sep = ";" if drop_frame else ":"
    return f"{hh:02d}:{mm:02d}:{ss:02d}{sep}{ff:02d}"


def to_vegas_csv(cues: list[SubtitleCue], fps: float = 29.97) -> str:
    """Genera el CSV nativo de Vegas para 'Insert Subtitles from File'.

    Formato CONFIRMADO en Vegas Pro 2026 (Boris FX): 4 columnas separadas por
    comas, con el texto en el último campo:

        Timecode Start, Timecode End, Timecode Length, Subtitle Text

    - El timecode es 'hh:mm:ss;ff' (drop-frame) o 'hh:mm:ss:ff' (no drop).
    - El texto va en el último campo, así que puede contener comas sin problema
      (Vegas toma todo lo posterior a la 3ª coma como texto).
    - El separador DEBE ser coma (un .txt con tabulaciones NO funciona: Vegas
      lo trata como "texto simple" y pierde los tiempos).
    """
    lines = []
    for cue in cues:
        start = seconds_to_timecode(cue.start, fps)
        end = seconds_to_timecode(cue.end, fps)
        length = seconds_to_timecode(max(cue.end - cue.start, 0.0), fps)
        # El CSV de Vegas es un registro por línea; los saltos de línea internos
        # se sustituyen por espacio para no romper el formato.
        text = cue.text.replace("\n", " ")
        lines.append(f"{start},{end},{length},{text}")
    return "\n".join(lines) + ("\n" if lines else "")


# ---------------------------------------------------------------------------
# Otros formatos
# ---------------------------------------------------------------------------

def _sbv_time(seconds: float) -> str:
    """Timecode de SBV: 'H:MM:SS.mmm' (horas sin cero a la izquierda)."""
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:d}:{m:02d}:{s:02d}.{ms:03d}"


def to_sbv(cues: list[SubtitleCue]) -> str:
    """Genera subtítulos en formato SBV (SubViewer, usado por YouTube).

    Formato: una línea 'inicio,fin' y debajo el texto, con línea en blanco.
    """
    blocks = []
    for cue in cues:
        blocks.append(f"{_sbv_time(cue.start)},{_sbv_time(cue.end)}\n{cue.text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _ttml_time(seconds: float) -> str:
    """Timecode de TTML: 'HH:MM:SS.mmm'."""
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def to_ttml(cues: list[SubtitleCue]) -> str:
    """Genera subtítulos en formato TTML (Timed Text Markup Language).

    Estándar XML usado en broadcast y streaming (Netflix, TV, DASH).
    """
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<tt xmlns="http://www.w3.org/ns/ttml" '
        'xmlns:tts="http://www.w3.org/ns/ttml#styling">',
        "  <head>",
        "    <styling>",
        '      <style xml:id="s1" tts:fontFamily="Arial" tts:fontSize="100%" '
        'tts:color="white" tts:backgroundColor="transparent" tts:textAlign="center"/>',
        "    </styling>",
        "  </head>",
        "  <body>",
        "    <div>",
    ]
    for cue in cues:
        begin = _ttml_time(cue.start)
        end = _ttml_time(cue.end)
        text = _escape_xml(cue.text).replace("\n", "<br/>")
        lines.append(f'      <p style="s1" begin="{begin}" end="{end}">{text}</p>')
    lines += [
        "    </div>",
        "  </body>",
        "</tt>",
    ]
    return "\n".join(lines) + "\n"
