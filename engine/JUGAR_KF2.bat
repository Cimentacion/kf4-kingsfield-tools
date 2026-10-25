@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title King's Field II - Jugar un nivel en King's Field IV
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py
if "%PY%"=="" (
  echo No encuentro Python.
  pause
  exit /b 1
)
rem --- Librerias de Python que hacen falta (numpy y Pillow): se instalan solas la primera vez ---
%PY% -c "import numpy, PIL" >nul 2>nul || (
  echo Instalando numpy y Pillow para Python, solo esta vez...
  %PY% -m pip install --user numpy pillow
)

rem Donde esta King's Field II (el .cue, el .bin o su carpeta). Tambien puedes arrastrar el .cue encima.
set "KF2=%USERPROFILE%\Downloads\King's Field II"
if exist "%USERPROFILE%\Downloads\King's Field (Europe)" set "KF2=%USERPROFILE%\Downloads\King's Field (Europe)"
if not "%~1"=="" set "KF2=%~1"
echo.
echo King's Field (europeo, el 2 japones): mapas 0 1 3 5 6 7 con sus modelos reales (2 y 4 aun no caben).
echo King's Field II (USA, el 3 japones): niveles 0 a 26.
echo Se usa el de la carpeta: "%KF2%"
set /p NIVEL=Que nivel porto? 
echo.
set EQ=n
set /p EQ=Quieres cambiar el equipo con el que empiezas (armas, escudos, objetos, magias)? s/n: 
if /i "%EQ%"=="s" (
  echo Se abre el Bloc de notas: quita el # de lo que quieras, guarda y cierralo para seguir.
  start "" /wait notepad "%~dp0equipo_inicial.txt"
)
if exist mapa_torre.json copy /y mapa_torre.json mapa_torre_antes_kf2.json >nul
%PY% kf2_a_editor.py "%KF2%" %NIVEL% mapa_torre.json
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo Tu mapa anterior esta en mapa_torre_antes_kf2.json. Generando y abriendo el juego...
call JUGAR_VALLE.bat editor
