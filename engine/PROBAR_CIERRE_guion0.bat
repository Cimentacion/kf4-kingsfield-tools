@echo off
rem Prueba del cierre de las puertas (sin el pulpo): KF_CIERRE=guion0
cd /d "%~dp0"
set KF_QUITAR=pulpo
set KF_CIERRE=guion0
call JUGAR_VALLE.bat editor
