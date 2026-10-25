@echo off
cd /d "%~dp0"
title King's Field IV - Extraer HUD y menu
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py
if "%PY%"=="" (
  echo No encuentro Python.
  pause
  exit /b 1
)
%PY% kf4_extraer_menu.py
echo.
echo Adjunta kf4_menu.zip en el chat.
pause
