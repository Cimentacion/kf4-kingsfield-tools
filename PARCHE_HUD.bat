@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title King's Field IV - Patch: HUD and controls
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py
if "%PY%"=="" (
  echo Python not found. Install it from python.org and tick "Add Python to PATH".
  pause
  exit /b 1
)
%PY% -c "import numpy" >nul 2>nul || (
  echo Installing numpy for Python, only this time...
  %PY% -m pip install --user numpy
)
rem The ISO: drag it onto this .bat, or "King's Field IV.iso" is looked for in this folder and in Downloads
set "ISO=%~1"
if "%ISO%"=="" if exist "King's Field IV.iso" set "ISO=King's Field IV.iso"
if "%ISO%"=="" if exist "%USERPROFILE%\Downloads\King's Field IV.iso" set "ISO=%USERPROFILE%\Downloads\King's Field IV.iso"
if "%ISO%"=="" (
  echo Drag your King's Field IV ISO ^(PAL, SLES-50920^) onto this .bat.
  pause
  exit /b 1
)
echo ISO: "%ISO%"
echo A patched copy is written next to it: "... (parche).iso". Your original ISO is not changed.
echo.
set OPC=
set R=y
echo Interface: HP shown as a number in the orb, weapon EXP bar in the equipment menu,
echo            weapons level up faster ^(70 and 140 hits instead of 180 and 480^).
set /p R=Do you want to patch the interface? y/n:
if /i not "%R%"=="y" set OPC=%OPC% --sin-hud
echo.
set R=n
echo Controls: left stick walks and strafes, right stick turns and looks up/down ^(like modern games^).
set /p R=Do you want to patch the game controls so they are more comfortable? y/n:
if /i "%R%"=="y" (
  set R2=n
  set /p R2=Invert looking up/down? y/n:
)
if /i "%R%"=="y" set OPC=%OPC% --dos-sticks
if /i "%R2%"=="y" set OPC=%OPC% --invertido
echo.
%PY% kf4_parche.py "%ISO%" %OPC%
echo.
pause
