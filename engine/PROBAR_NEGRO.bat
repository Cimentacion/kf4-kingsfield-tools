@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Buscar por que se queda en negro
echo.
echo Vuelve a generar el mapa que portaste (mapa_torre.json) quitando una parte, para ver cual cuelga el juego.
echo Prueba en este orden y dime con cual arranca:
echo.
echo   1  sin el agua animada (el agua va con las demas texturas, quieta)
echo   2  sin el cielo
echo   3  sin los enemigos
echo   4  sin cofres, puertas ni paredes que se abren
echo   5  sin nada de lo anterior (agua, cielo, enemigos y objetos)
echo   6  como estaba antes de hoy (sin agua animada, sin cielo, luz y texturas como antes)
echo   7  la 6 y ademas: vuelve a portar el nivel con los escalones de antes y sin el indice nuevo
echo   8  la 6 y ademas: sin el indice nuevo (los escalones nuevos)
echo   9  la 7 y sin enemigos
echo  10  la 7 pero con el cielo puesto (sin nubes animadas), como la version que te funciono
echo  11  todos los enemigos como escarabajos
echo  12  solo 8 enemigos (los tipos de verdad)
echo  13  solo los esqueletos altos      14  solo los escarabajos del nivel
echo  15  solo los murcielagos           16  solo las armaduras vivientes
echo  17  todos los enemigos con los datos del escarabajo del Palacio (cambia solo el bicho)
echo  18  la 17 pero solo murcielagos
echo  19  un solo escarabajo del Palacio, a 3 m de donde empiezas
echo  20  un solo esqueleto alto, a 3 m de donde empiezas
echo  21  un solo murcielago, a 3 m de donde empiezas
echo.
set /p OPCION=Cual pruebo? 
set KF_QUITAR=
if "%OPCION%"=="1" set KF_QUITAR=agua
if "%OPCION%"=="2" set KF_QUITAR=cielo
if "%OPCION%"=="3" set KF_QUITAR=enemigos
if "%OPCION%"=="4" set KF_QUITAR=objetos
if "%OPCION%"=="5" set KF_QUITAR=agua,cielo,enemigos,objetos
if "%OPCION%"=="6" set KF_QUITAR=agua,cielo,luz,texturas
if "%OPCION%"=="7" set KF_QUITAR=agua,cielo,luz,texturas,indice
if "%OPCION%"=="8" set KF_QUITAR=agua,cielo,luz,texturas,indice
if "%OPCION%"=="9" set KF_QUITAR=agua,cielo,luz,texturas,indice,enemigos
if "%OPCION%"=="10" set KF_QUITAR=agua,nubes,luz,texturas,indice
if "%OPCION%"=="11" set KF_QUITAR=tipos
if "%OPCION%"=="12" set KF_QUITAR=pocos
if "%OPCION%"=="13" set KF_QUITAR=solo58
if "%OPCION%"=="14" set KF_QUITAR=solo39
if "%OPCION%"=="15" set KF_QUITAR=solo10
if "%OPCION%"=="16" set KF_QUITAR=solo24
if "%OPCION%"=="17" set KF_QUITAR=plantilla
if "%OPCION%"=="18" set KF_QUITAR=plantilla,solo10
if "%OPCION%"=="19" set KF_QUITAR=junto11
if "%OPCION%"=="20" set KF_QUITAR=junto58
if "%OPCION%"=="21" set KF_QUITAR=junto10
if not defined KF_QUITAR (
  echo Esa opcion no existe.
  pause
  exit /b 1
)
if "%OPCION%"=="7" goto portar
if "%OPCION%"=="8" goto portar
if "%OPCION%"=="9" goto portar
if "%OPCION%"=="10" goto portar
goto jugar
:portar
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py
set "KF2=%USERPROFILE%\Downloads\King's Field II"
if exist "%USERPROFILE%\Downloads\King's Field (Europe)" set "KF2=%USERPROFILE%\Downloads\King's Field (Europe)"
set RAMPAS=
if "%OPCION%"=="7" set RAMPAS=--sin-rampas
if "%OPCION%"=="9" set RAMPAS=--sin-rampas
if "%OPCION%"=="10" set RAMPAS=--sin-rampas
%PY% kf2_a_editor.py "%KF2%" mapa_torre.json %RAMPAS%
if errorlevel 1 (
  pause
  exit /b 1
)
:jugar
call JUGAR_VALLE.bat editor
