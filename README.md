# Subtítulos automáticos

Aplicación de escritorio que transcribe audio y video de forma **local** (sin
internet) usando **faster-whisper**, y genera subtítulos con tiempos para editores
de video en varios formatos: **SRT**, **SBV**, **ASS**, **TTML** y **CSV de Vegas**.

Pensada para editores: transcribes, revisas los subtítulos en una tabla editable
y exportas el formato que necesite tu editor (Premiere, CapCut, DaVinci, YouTube,
Vegas, etc.).

## Características

- Transcripción **local/offline** con Whisper (`large-v3`), GPU CUDA o CPU.
- **Formatos**: SRT, SBV, ASS, TTML y CSV de Vegas (con timecode `hh:mm:ss:ff`).
- **Traducción**: mantener original, inglés, japonés, chino, francés, portugués y
  coreano. Original e inglés vienen incluidos; los demás se descargan **bajo
  demanda** desde la propia app (offline, con Argos Translate).
- **Calidad/velocidad**: Rápido, Equilibrado y Máxima calidad.
- **Revisión antes de exportar**: tabla editable, cambio de mayúsculas/minúsculas,
  quitar puntuación, etc.
- **Guardar como**: eliges dónde guardar y el nombre del archivo.
- **Arrastrar y soltar** el archivo a la ventana.
- **Modo claro y oscuro**, con preferencias recordadas.
- **Actualizaciones automáticas** desde GitHub Releases, con barra de progreso,
  changelog y reapertura automática (no vuelve a descargar el modelo).
- **Log de la app** para diagnosticar errores.

## Requisitos

- Windows 10/11.
- Python 3.10 o superior (para desarrollo).
- GPU NVIDIA con CUDA (recomendado, p. ej. RTX 3060) para `large-v3`. También
  funciona en CPU (más lento).

## Instalación (desarrollo)

```powershell
# 1. Crear y activar un entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar dependencias
pip install -r requirements.txt
```

> La primera ejecución descarga el modelo `large-v3` (~3 GB) y lo guarda en
> caché local. Necesitas internet solo esa primera vez.

### Activar la GPU (NVIDIA)

`ctranslate2` necesita **cuBLAS 12**, que no viene con el driver de NVIDIA ni con
el wheel de `ctranslate2`. En Windows, instálalo por pip (queda dentro del `.venv`):

```powershell
.\.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cuda-runtime-cu12
```

La app registra automáticamente esas DLLs en el `PATH` al iniciar. Sin esto, al
transcribir verás `Error: Library cublas64_12.dll is not found`. Si no tienes GPU
NVIDIA, la app usa CPU automáticamente.

## Uso

### Interfaz gráfica (recomendado)

```powershell
python gui.py
```

Flujo: **elige el archivo (o arrástralo) → ajusta palabras por línea, idioma,
calidad y formato → Transcribir → revisa → exporta donde quieras**.

Formatos disponibles:

| Formato | Para qué |
|---|---|
| **SRT** | Universal: Premiere, CapCut, DaVinci Resolve, YouTube |
| **SBV** | YouTube (SubViewer) |
| **ASS** | Anime / fansubs: fuentes, colores y posiciones |
| **TTML** | Broadcast y streaming (Netflix, TV, DASH) |
| **CSV** | Sony Vegas (`Insert > Insert Subtitles from File`) |

> Hay una versión avanzada con editor completo (tabla, forma de onda y ajustes):
> `python gui_avanzada.py`.

### Consola

```powershell
# Básico: transcribe y genera video.srt + video.ass + video.vegas.csv
python app.py video.mp4

# Ajustar largo de frases y pausas
python app.py video.mp4 --max-words 2 --max-gap 0.3

# Solo SRT
python app.py video.mp4 --no-ass --no-vegas

# Salida con otro nombre
python app.py video.mp4 -o C:\subtitulos\episodio1
```

### Opciones principales (CLI)

| Opción | Por defecto | Descripción |
|---|---|---|
| `--model` | `large-v3` | Tamaño del modelo (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `--language` | `es` | Idioma (`es`, `en`, ...). `auto` para detectar |
| `--device` | `auto` | `auto`, `cuda` o `cpu` |
| `--max-words` | `3` | Máx. palabras por línea |
| `--max-chars` | `18` | Tope de caracteres por línea |
| `--max-gap` | `0.4` | Pausa (s) que corta una línea |
| `--min-duration` | `0.3` | Duración mínima de una línea (s) |
| `--max-duration` | `4.0` | Duración máxima de una línea (s) |
| `--fps` | `60` | FPS para el CSV de Vegas |
| `--no-vegas` | — | No exportar el `.csv` para Vegas |

## Actualizaciones

La app busca actualizaciones en GitHub Releases al abrir. Si hay una nueva
versión, muestra un banner con botón **Actualizar**, descarga el paquete (sin el
modelo de IA), muestra la barra de progreso y el changelog, y se reinicia sola al
terminar.

## Logs

Los logs se guardan en:
`%LOCALAPPDATA%\SubtitulosAutomaticos\logs\app.log`.

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
│   ├── exporters.py    # SRT, ASS, SBV, TTML y CSV de Vegas
│   ├── translator.py   # traducción offline (Argos) bajo demanda
│   ├── updater.py      # actualizaciones desde GitHub Releases
│   ├── version.py      # versión de la app
│   └── logging_setup.py# log de la app
├── gui/
│   ├── simple_window.py  # ventana simple
│   ├── main_window.py    # ventana avanzada (tabla + ajustes + export)
│   ├── review_dialog.py  # revisión de subtítulos antes de exportar
│   ├── waveform.py       # forma de onda con reproducción
│   ├── worker.py         # transcripción en hilo aparte
│   └── timeutil.py       # parseo/formato de tiempos
└── requirements.txt
```

## Roadmap

1. ✅ Backend de transcripción + exportación (SRT/ASS/SBV/TTML/Vegas).
2. ✅ Interfaz gráfica simple (revisión, traducción, calidad, formatos).
3. ✅ Actualizaciones automáticas y log de la app.
4. ⏳ Estilos ASS avanzados, preview y atajos extra.
