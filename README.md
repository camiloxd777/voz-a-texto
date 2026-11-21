# Subtítulos automáticos (estilo Premiere) para Sony Vegas

Aplicación de escritorio que transcribe audio/video de forma **local** (sin
internet) usando **faster-whisper** y genera subtítulos en **SRT**, **ASS** y
**CSV nativo de Vegas**, listos para importar en Sony Vegas.

Incluye una **interfaz gráfica** (tabla editable, forma de onda y reproducción)
además del modo consola.

## Requisitos

- Windows 10/11, Python 3.10 o superior.
- GPU NVIDIA con CUDA (recomendado, p. ej. RTX 3060) para el modelo `large-v3`.
  También funciona en CPU (más lento, con `--device cpu`).

## Instalación

```powershell
# 1. Crear y activar un entorno virtual (recomendado)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar dependencias
pip install -r requirements.txt
```

> La primera ejecución descarga el modelo `large-v3` (~3 GB) y lo guarda en
> caché local. Necesitas internet solo esa primera vez.

### Activar la GPU (NVIDIA)

`ctranslate2` compila contra CUDA 12 y necesita **cuBLAS 12**, que **no** viene
ni en el driver de NVIDIA ni en el wheel de `ctranslate2`. En Windows, instala
las librerías por pip y listo (quedan dentro del `.venv`, sin tocar el sistema):

```powershell
.\.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cuda-runtime-cu12
```

La app registra automáticamente esas DLLs en el `PATH` al iniciar (ver
`core/transcriber.py`), así que no necesitas nada más. Sin esto, al transcribir
saldría `Error: Library cublas64_12.dll is not found`. Si no tienes GPU NVIDIA,
usa `--device cpu`.

## Uso

### Interfaz gráfica (recomendado)

```powershell
python gui.py
```

Flujo simple: **Selecciona el audio/video → elige palabras por línea y formato →
Transcribir** (ves el progreso) → te da la ruta del archivo generado.

Formatos disponibles (con mini leyenda en la propia app):

| Formato | Para qué |
|---|---|
| **CSV** | Sony Vegas (`Insert > Insert Subtitles from File`) |
| **SRT** | Universal: Premiere, CapCut, DaVinci Resolve, YouTube |
| **SBV** | YouTube (SubViewer) |
| **ASS** | Anime / fansubs: fuentes, colores y posiciones |
| **TTML** | Broadcast y streaming (Netflix, TV, DASH) |

> ¿Quieres más control? Hay una versión avanzada con editor completo
> (tabla, forma de onda y ajustes): `python gui_avanzada.py`.

### Consola

```powershell
# Básico: transcribe y genera video.srt + video.ass + video.vegas.csv
python app.py video.mp4

# Ajustar largo de frases y pausas
python app.py video.mp4 --max-words 2 --max-gap 0.3

# Solo SRT (sin ASS ni Vegas)
python app.py video.mp4 --no-ass --no-vegas

# Salida con otro nombre
python app.py video.mp4 -o C:\subtitulos\episodio1
```

### Opciones principales

| Opción | Por defecto | Descripción |
|---|---|---|
| `--model` | `large-v3` | Tamaño del modelo (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `--language` | `es` | Idioma (`es`, `en`, ...). `auto` para detectar |
| `--device` | `auto` | `auto`, `cuda` o `cpu` |
| `--max-words` | `3` | Máx. palabras por línea (frases cortas, estilo guion) |
| `--max-chars` | `18` | Tope de caracteres por línea (seguridad) |
| `--max-gap` | `0.4` | Pausa (s) que corta una línea |
| `--min-duration` | `0.3` | Duración mínima de una línea (s) |
| `--max-duration` | `4.0` | Duración máxima de una línea (s) |
| `--fps` | `60` | FPS del proyecto de Vegas (debe coincidir; 29.97 = SMPTE Drop) |
| `--no-vegas` | — | No exportar el `.csv` para Vegas |

## Importar en Sony Vegas (con la duración correcta)

Vegas **no importa bien el `.srt`** como eventos con duración. Para que cada
subtítulo entre en la línea de tiempo **con su tiempo de inicio y fin exactos**,
usa el archivo `.vegas.csv` que genera la app (formato nativo de Vegas):

1. En Vegas, coloca tu video en la línea de tiempo.
2. Menú **Insert > Insert Subtitles from File**.
3. Haz clic en **Browse** y selecciona el archivo **`tu_video.vegas.csv`**.
4. Elige el preset de texto que prefieras y pulsa **OK**.

Vegas crea una pista nueva con un **evento de texto por subtítulo**, ya
sincronizado (nada de los 5 segundos fijos que salen al importar texto plano).

> Formato **confirmado** en Vegas Pro 2026 (Boris FX): 4 columnas separadas por
> **comas** — `Start, End, Length, Text` — con timecode `hh:mm:ss;ff`
> (drop-frame) o `hh:mm:ss:ff` (no drop). El texto va en el último campo, así
> que puede contener comas.
>
> **⚠️ Ojo:** el separador debe ser **coma** (un `.txt` con tabulaciones NO
> funciona: Vegas lo trata como "texto simple" y pierde los tiempos).
>
> **⚠️ Importante:** el `--fps` debe coincidir con el frame rate de TU proyecto
> de Vegas, o Vegas no reconocerá los timecodes y los mostrará como texto.
> Por ejemplo: proyecto a 60 fps → `--fps 60` (por defecto); a 25 (PAL) →
> `--fps 25`; a 29.97 → `--fps 29.97`.

- **SRT**: formato universal (para YouTube, Subtitle Edit, etc.).
- **ASS**: subtítulos con estilo (fuente, color, contorno) para herramientas tipo Aegisub.

## Estructura

```
subtitulos/
├── app.py              # CLI (punto de entrada)
├── gui.py              # Interfaz simple (punto de entrada)
├── gui_avanzada.py     # Interfaz avanzada (editor completo)
├── core/
│   ├── audio.py        # extracción de audio con ffmpeg
│   ├── transcriber.py  # faster-whisper (GPU/CPU)
│   ├── subtitles.py    # modelo de datos + post-procesado
│   └── exporters.py    # SRT, ASS y CSV nativo de Vegas
├── gui/
│   ├── simple_window.py  # ventana simple (subir + transcribir + CSV)
│   ├── main_window.py    # ventana avanzada (tabla + ajustes + export)
│   ├── waveform.py       # forma de onda con reproducción
│   ├── worker.py         # transcripción en hilo aparte
│   └── timeutil.py       # parseo/formato de tiempos
└── requirements.txt
```

## Roadmap

1. ✅ Fase 1: backend de transcripción + exportación SRT/ASS/Vegas.
2. ✅ Fase 2: interfaz gráfica (tabla editable + waveform + ajustes).
3. ⏳ Fase 3: estilos ASS avanzados, preview, atajos extra.
