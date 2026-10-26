@echo off
rem Prueba del cierre de las puertas (sin el pulpo): KF_CIERRE=abierta
cd /d "%~dp0"
set KF_QUITAR=pulpo
set KF_CIERRE=abierta
call JUGAR_VALLE.bat editor
