; Script de Inno Setup para "Subtítulos automáticos" (creado por masku)
; Incluye la app (exe + dependencias) y el modelo de IA Whisper large-v3 (~3 GB).
; Muestra un aviso antes de instalar explicando el modelo y por qué se incluye.
;
; Requisitos para compilar:
;   - Inno Setup 6 (https://jrsoftware.org/isinfo.php)
;   - Haber generado la app:  .\.venv\Scripts\python.exe -m PyInstaller --noconfirm subtitulos.spec
;   - Tener el modelo en caché de Hugging Face (ruta en ModelSource abajo)

#define MyAppName "Subtitulos Automaticos"
#define MyAppVersion "1.4.0"
#define MyAppPublisher "masku"
#define MyAppExeName "subtitulos.exe"

; Carpeta del proyecto y origen del modelo.
; Coloca (o enlaza) el modelo en: <ProjectDir>\models\faster-whisper-large-v3
; (debe contener model.bin, config.json, tokenizer.json, etc.)
#define ProjectDir ".."
#define ModelSource "{#ProjectDir}\models\faster-whisper-large-v3"

[Setup]
; ID fijo para que futuras versiones actualicen la misma instalación
AppId={{D7E6A7F2-6B8D-4D47-9E1F-2C5C0A5B9A10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=
AppSupportURL=
AppUpdatesURL=
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Instalar solo para el usuario actual (sin opción "para todos los usuarios")
PrivilegesRequired=lowest
; Aviso: se instalará el modelo de IA (~3 GB) y la razón
InfoBeforeFile={#ProjectDir}\installer\modelo_ia_aviso.txt
; Salida del instalador
OutputDir={#ProjectDir}\installer_output
OutputBaseFilename=SubtitulosAutomaticos_Setup
SetupIconFile={#ProjectDir}\assets\app_icon.ico
Compression=lzma2/max
SolidCompression=yes
DiskSpanning=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; App completa (exe + _internal con Python, librerías, CUDA, ffmpeg, etc.)
Source: "{#ProjectDir}\dist\subtitulos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Modelo de IA Whisper large-v3 (~3 GB) para transcripción local sin internet
Source: "{#ModelSource}\*"; DestDir: "{app}\models\faster-whisper-large-v3"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
