@echo off
rem Prueba: el mismo mapa (mapa_torre.json) con el pulpo pero sin el guion nuevo que cierra las puertas.
cd /d "%~dp0"
set KF_QUITAR=cierre
call JUGAR_VALLE.bat editor
