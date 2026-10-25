"""FIELDIV-ENGINE - lanzador.

Menú de consola que abre las herramientas de la carpeta engine\ (los .bat de siempre). Se compila a
FIELDIV-ENGINE.exe con PyInstaller (.github/workflows/build.yml). Las herramientas siguen necesitando Python
instalado: el .exe solo es la puerta de entrada.

Carpetas (junto al .exe):
    FIELDIV-ENGINE.exe
    CHANGELOG.txt
    engine\            las herramientas
    King's Field IV.iso   (tu copia; también vale dentro de engine\)
"""

import os
import subprocess
import sys

VERSION = "Alpha 0.1"

OPCIONES = [
    ("1", "Portar un nivel de King's Field y jugarlo", "JUGAR_KF2.bat"),
    ("2", "Editor de mapas", "EDITOR.bat"),
    ("3", "Generar el valle del acantilado y jugarlo", "JUGAR_VALLE.bat"),
    ("4", "Parche de HUD y controles para tu ISO (sin cambiar mapas)", "PARCHE_HUD.bat"),
    ("5", "Ver el changelog", None),
]


def base():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    raiz = base()
    engine = os.path.join(raiz, "engine")
    os.system("title FIELDIV-ENGINE " + VERSION)
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 60)
        print(f"  FIELDIV-ENGINE  {VERSION}   -   King's Field IV (PS2)")
        print("=" * 60)
        if not os.path.isdir(engine):
            print("\nNo encuentro la carpeta 'engine' junto al .exe. Descomprime el zip entero.")
            input("\nPulsa Intro para salir...")
            return
        for k, texto, _ in OPCIONES:
            print(f"  [{k}] {texto}")
        print("  [0] Salir")
        r = input("\nElige una opcion: ").strip()
        if r == "0":
            return
        for k, texto, bat in OPCIONES:
            if r != k:
                continue
            if bat is None:
                log = os.path.join(raiz, "CHANGELOG.txt")
                if os.name == "nt":
                    subprocess.Popen(["notepad.exe", log])
                else:
                    print(open(log, encoding="utf-8").read())
                    input("\nIntro para volver...")
            else:
                ruta = os.path.join(engine, bat)
                if not os.path.isfile(ruta):
                    print(f"No encuentro {bat} en engine\\")
                    input("Intro para volver...")
                else:
                    subprocess.call(["cmd", "/c", ruta], cwd=engine)
            break


if __name__ == "__main__":
    main()
