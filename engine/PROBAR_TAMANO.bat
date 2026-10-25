@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Prueba: el prologo con el mapa hecho mas grande
echo.
echo Genera el prologo (que te funciona) pero con el mapa inflado con relleno vacio,
echo para ver si el juego se cuelga solo por el tamano del mapa.
echo.
echo   1  prologo + 1,5 MB de relleno (unos 5,5 MB, mas que su sitio original)
echo   2  prologo + 0,3 MB de relleno (todavia cabe en su sitio original)
echo.
set /p OPCION=Cual pruebo? 
set KF_RELLENO=
if "%OPCION%"=="1" set KF_RELLENO=1.5
if "%OPCION%"=="2" set KF_RELLENO=0.3
if not defined KF_RELLENO (
  echo Esa opcion no existe.
  pause
  exit /b 1
)
call JUGAR_VALLE.bat prologo
