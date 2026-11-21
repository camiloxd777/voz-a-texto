"""Punto de entrada (CLI) de la Fase 1: transcripción y exportación.

Uso de ejemplo:

    python app.py video.mp4
    python app.py video.mp4 --model large-v3 --language es --max-chars 42
    python app.py video.mp4 --no-ass --srt

Genera por defecto `<nombre>.srt`, `<nombre>.ass` y `<nombre>.vegas.csv`
(este último para importar en Vegas con la duración correcta) junto al origen.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from core.audio import extract_audio_for_transcription
from core.exporters import AssStyle, to_ass, to_srt, to_vegas_csv
from core.subtitles import build_cues, words_from_segments
from core.transcriber import Transcriber


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Subtítulos automáticos con Whisper local (SRT + ASS).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("input", help="Archivo de video o audio a transcribir.")
    p.add_argument(
        "-o", "--output",
        help="Ruta base de salida (sin extensión). Por defecto, junto al origen.",
    )
    p.add_argument("--model", default="large-v3", help="Tamaño del modelo Whisper.")
    p.add_argument("--language", default="es", help="Idioma (es, en, ...). 'auto' para detectar.")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    p.add_argument("--max-words", type=int, default=3, help="Máx. palabras por cue (estilo guion).")
    p.add_argument("--max-lines", type=int, default=1, choices=[1, 2], help="Número de líneas por cue (1 o 2).")
    p.add_argument("--max-chars", type=int, default=18, help="Tope de caracteres por línea (seguridad).")
    p.add_argument("--max-gap", type=float, default=0.4, help="Pausa (s) que corta una línea.")
    p.add_argument("--min-duration", type=float, default=0.3, help="Duración mínima (s).")
    p.add_argument("--max-duration", type=float, default=4.0, help="Duración máxima (s).")
    p.add_argument("--no-srt", action="store_true", help="No exportar .srt.")
    p.add_argument("--no-ass", action="store_true", help="No exportar .ass.")
    p.add_argument("--no-vegas", action="store_true", help="No exportar el .csv para Vegas.")
    p.add_argument(
        "--fps", type=float, default=60.0,
        help="FPS del proyecto de Vegas (debe coincidir; 29.97 = SMPTE Drop).",
    )
    p.add_argument("--keep-audio", action="store_true", help="No borrar el WAV temporal.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: no existe el archivo '{input_path}'", file=sys.stderr)
        return 1

    language = None if args.language == "auto" else args.language

    audio_path = None
    try:
        print(f"[1/4] Extrayendo audio de {input_path.name} ...")
        audio_path = extract_audio_for_transcription(input_path)

        print(f"[2/4] Cargando modelo '{args.model}' ({args.device}) ...")
        t0 = time.time()
        transcriber = Transcriber(
            model_size=args.model,
            device=args.device,
        )
        print(f"      -> dispositivo: {transcriber.device} / "
              f"compute: {transcriber.compute_type} "
              f"({time.time() - t0:.1f}s)")

        print("[3/4] Transcribiendo ...")
        t0 = time.time()
        segments, info = transcriber.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=True,
        )
        print(f"      -> idioma: {info['language']} "
              f"(prob. {info['language_probability']:.2f}), "
              f"duración: {info['duration']:.1f}s "
              f"({time.time() - t0:.1f}s)")

        words = [w for seg in segments for w in seg.words]
        if not words:
            print("Aviso: no se detectaron palabras con marcas de tiempo.", file=sys.stderr)
            words = words_from_segments(segments)

        cues = build_cues(
            words,
            max_words=args.max_words,
            max_chars=args.max_chars,
            max_gap=args.max_gap,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            max_lines=args.max_lines,
        )
        print(f"      -> {len(cues)} líneas de subtítulo generadas.")

        base = Path(args.output) if args.output else input_path.with_suffix("")
        written = []

        print("[4/4] Exportando ...")
        if not args.no_srt:
            srt_path = base.with_suffix(".srt")
            srt_path.write_text(to_srt(cues), encoding="utf-8")
            written.append(srt_path)

        if not args.no_ass:
            ass_path = base.with_suffix(".ass")
            ass_path.write_text(to_ass(cues), encoding="utf-8")
            written.append(ass_path)

        if not args.no_vegas:
            vegas_path = base.with_suffix(".vegas.csv")
            vegas_path.write_text(to_vegas_csv(cues, fps=args.fps), encoding="utf-8")
            written.append(vegas_path)

        if not written:
            print("No se exportó ningún archivo (--no-srt, --no-ass y --no-vegas).", file=sys.stderr)
            return 1

        for p in written:
            print(f"      -> {p}")

        print("\nListo.")
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if audio_path and audio_path.exists() and not args.keep_audio:
            try:
                audio_path.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
