@echo off
rem Prueba: el mismo mapa (mapa_torre.json) como en la revision 7: sin el pulpo y sin el guion nuevo que cierra las puertas.
cd /d "%~dp0"
set KF_QUITAR=pulpo,cierre
call JUGAR_VALLE.bat editor
