@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title King's Field IV - PRUEBA sin parches del ejecutable

rem ================= AJUSTES =================
rem SEMILLA: cambia el numero para otro valle distinto.
rem DEBUG=1: Partida nueva con nivel alto y carrera rapida (para probar). DEBUG=0: partida normal.
set SEMILLA=1
rem ZONA: editor (el mapa que hagas en el Editor de La Torre, guardado como MAPA),
rem       prologo (casita, aldea, puente y la torre) o valle (el valle del acantilado).
set ZONA=editor
rem (el editor local llama a este .bat con la zona como argumento: JUGAR_VALLE.bat editor)
if not "%~1"=="" set ZONA=%~1
set MAPA=mapa_torre.json
set DEBUG=1
rem GIRO: velocidad de giro de la camara (1 = la del juego original).
set GIRO=1
rem MANDO: dos_sticks (izquierdo andar/paso lateral, derecho girar/mirar),
rem        dos_sticks_invertido (igual, con la vista vertical al reves) u original.
set MANDO=original
rem VIDA_NUMERO: 1 = la vida en numero dentro del orbe rojo, 0 = HUD original.
set VIDA_NUMERO=0
rem CRUZ: 1 = cruz de equipo rapido con la cruceta (derecha arma, izquierda escudo, arriba consumible), 0 = no.
set CRUZ=0
rem EXP: 1 = barra de experiencia del arma en el menu de equipo, 0 = menu original.
set EXP=0
rem Donde esta tu PCSX2:
set "PCSX2_FIJO=C:\Users\usuario\Downloads\pcsx2-v2.9.127-windows-x64-Qt\pcsx2-qt.exe"
rem ===========================================

rem --- Python ---
set PY=
where python >nul 2>nul && set PY=python
if not defined PY where py >nul 2>nul && set PY=py
if not defined PY (
  echo No encuentro Python. Instalalo desde python.org marcando "Add python.exe to PATH".
  pause
  exit /b 1
)

rem --- Cerrar PCSX2 si esta abierto: la ISO no se puede actualizar mientras se juega ---
for %%E in (pcsx2-qt.exe pcsx2.exe pcsx2x64.exe pcsx2-avx2.exe) do (
  tasklist /FI "IMAGENAME eq %%E" 2>nul | find /I "%%E" >nul && (
    echo Cerrando PCSX2 para poder actualizar la ISO...
    taskkill /IM %%E /F >nul 2>nul
    timeout /t 2 /nobreak >nul
  )
)

rem --- PRUEBA: se borra la ISO (valle) para copiarla de nuevo limpia ---
for %%F in ("*(valle).iso") do (
  echo Borrando %%F para copiarla de nuevo...
  del /f /q "%%F"
)

rem --- Generar el mapa e inyectarlo en la ISO ---
set OPC=--semilla %SEMILLA% --zona %ZONA% --mapa "%MAPA%" --giro %GIRO% --mando %MANDO%
if "%VIDA_NUMERO%"=="0" set OPC=%OPC% --sin-vida-numero
if "%CRUZ%"=="0" set OPC=%OPC% --sin-cruz
if "%EXP%"=="0" set OPC=%OPC% --sin-exp
if "%DEBUG%"=="1" set OPC=%OPC% --debug
echo Opciones: %OPC%
%PY% kf4_valle.py %OPC%
if errorlevel 1 (
  echo.
  echo Algo ha fallado. Haz una captura de esta ventana y mandamela.
  pause
  exit /b 1
)
set /p ISO=<kf4_valle\iso_lista.txt

rem --- Localizar PCSX2 (la ruta se recuerda en pcsx2_ruta.txt) ---
set PCSX2=
if exist "%PCSX2_FIJO%" set "PCSX2=%PCSX2_FIJO%"
if not defined PCSX2 if exist pcsx2_ruta.txt set /p PCSX2=<pcsx2_ruta.txt
if defined PCSX2 if not exist "!PCSX2!" set PCSX2=
if not defined PCSX2 (
  for %%P in ("%ProgramFiles%\PCSX2\pcsx2-qt.exe" "%ProgramFiles%\PCSX2\pcsx2.exe" "%LOCALAPPDATA%\Programs\PCSX2\pcsx2-qt.exe" "%USERPROFILE%\Documents\PCSX2\pcsx2-qt.exe" "C:\PCSX2\pcsx2-qt.exe" "C:\PCSX2\pcsx2.exe") do (
    if not defined PCSX2 if exist %%P set "PCSX2=%%~P"
  )
)
if not defined PCSX2 (
  echo.
  echo No encuentro PCSX2. Arrastra aqui su archivo .exe y pulsa Enter:
  set /p PCSX2=
  set "PCSX2=!PCSX2:"=!"
)
if not exist "!PCSX2!" (
  echo No existe "!PCSX2!".
  pause
  exit /b 1
)
> pcsx2_ruta.txt echo !PCSX2!

echo.
echo Abriendo PCSX2 con el valle. En el menu del juego elige Partida nueva.
start "" "!PCSX2!" "!ISO!"
echo.
echo Haz una captura de esta ventana y mandamela.
pause
exit /b 0
