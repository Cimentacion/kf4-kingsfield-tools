@echo off
cd /d "%~dp0"
title King's Field IV - Exportar texturas para el editor
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py
if "%PY%"=="" (
  echo No encuentro Python.
  pause
  exit /b 1
)
%PY% -c "import numpy" >nul 2>nul || (
  echo Instalando numpy, solo la primera vez...
  %PY% -m pip install --user numpy
)
%PY% kf4_texturas.py
echo.
echo Solo hace falta para el editor online. Con EDITOR.bat las texturas se cargan solas.
pause
