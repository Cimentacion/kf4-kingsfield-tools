@echo off
cd /d "%~dp0"
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py
set "KF1=%USERPROFILE%\Downloads\King's Field (Europe)"
if not "%~1"=="" set "KF1=%~1"
%PY% kf1_sacar_talk.py "%KF1%"
pause
