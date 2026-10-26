@echo off
rem Prueba: genera el mismo mapa (mapa_torre.json) pero con serpientes en vez del pulpo, para ver si el cuelgue es del pulpo.
cd /d "%~dp0"
set KF_QUITAR=pulpo
call JUGAR_VALLE.bat editor
