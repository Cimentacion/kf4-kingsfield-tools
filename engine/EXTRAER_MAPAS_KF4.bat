@echo off
cd /d "%~dp0"
title King's Field IV - Extraer mapas (cielo, cofres, puertas)
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py
if "%PY%"=="" (
  echo No encuentro Python.
  pause
  exit /b 1
)
%PY% kf4_extraer_mapas.py
echo.
echo Adjunta kf4_mapas_cielo.zip en el chat.
pause
