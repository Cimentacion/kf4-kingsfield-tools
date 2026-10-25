@echo off
cd /d "%~dp0"
title King's Field II - Extraer datos para portar mapas
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py
if "%PY%"=="" (
  echo No encuentro Python.
  pause
  exit /b 1
)
rem Sin argumento busca en Descargas\King's Field II. Tambien puedes arrastrar el .cue encima de este .bat.
if "%~1"=="" (
  %PY% kf2_extraer.py
) else (
  %PY% kf2_extraer.py "%~1"
)
echo.
echo Adjunta kf2_datos.zip en el chat.
pause
