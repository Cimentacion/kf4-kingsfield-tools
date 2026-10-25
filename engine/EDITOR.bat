@echo off
cd /d "%~dp0"
title Editor de La Torre (cierra esta ventana para salir)
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py
if "%PY%"=="" (
  echo No encuentro Python.
  pause
  exit /b 1
)
rem Las texturas se leen con numpy: si no esta, se instala una vez
%PY% -c "import numpy, PIL" >nul 2>nul || (
  echo Instalando numpy y Pillow, solo la primera vez...
  %PY% -m pip install --user numpy pillow
)
%PY% kf4_editor_local.py
pause
