#!/usr/bin/env python3
"""
kf4_extraer_menu.py - Empaqueta las texturas del HUD y del menú y los modelos de objetos del menú de tu ISO
de King's Field IV en kf4_menu.zip, para hacer la cruz de equipo con las piezas del propio juego.

Uso: doble clic en EXTRAER_MENU.bat (o: python kf4_extraer_menu.py [ruta de la ISO]).
Mete en el zip:
  - menu/menu.tmx, sfx/sfx.tmx, sfx/sfx2.tmx, font.* y los *_para.dat del menú (tal cual);
  - las ilustraciones de objetos (menu/select2/iXXXX.mod) y, si caben, los modelos 3D del menú;
  - lista.txt con todos los nombres y tamaños de la carpeta menu/ y sfx/.
"""

import os
import sys
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import kf4_mapdump as md     # noqa: E402

LIMITE = 40 * 1024 * 1024    # que el zip se pueda adjuntar


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        iso = os.path.abspath(args[0])
    else:
        isos = [f for f in os.listdir(AQUI) if f.lower().endswith(".iso") and "(valle)" not in f]
        isos.sort(key=lambda f: ("(" in f, len(f), f))
        if not isos:
            print("No encuentro la ISO de King's Field IV en esta carpeta.")
            return 1
        iso = os.path.join(AQUI, isos[0])
    print("Leyendo", os.path.basename(iso))
    src = md.Source(iso)
    nombres = sorted(n for n in src.names if n.startswith(("menu/", "sfx/", "font", "title/")))
    lista = []
    for n in nombres:
        v = src.names[n]
        lista.append(f"{n}\t{v[1] if isinstance(v, tuple) else os.path.getsize(v)}")
    # primero lo pequeño e importante, luego los modelos hasta el límite
    primero = [n for n in nombres if n.endswith((".tmx", ".tmr", ".txc", ".dat", ".mi2"))
               and not n.startswith("title/")]
    # las ilustraciones 2D de cada objeto van dentro de menu/select2/iXXXX.mod: lo primero
    modelos = sorted((n for n in nombres if n.endswith(".mod")), key=lambda n: (not n.startswith("menu/select2/"), n))
    salida = os.path.join(AQUI, "kf4_menu.zip")
    total = 0
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("lista.txt", "\n".join(lista))
        for n in primero + modelos:
            datos = src.read(n)
            if total + len(datos) > LIMITE:
                print("  (zip lleno, paro en", n, ")")
                break
            z.writestr(n, datos)
            total += len(datos)
    print(f"Hecho: {salida}  ({os.path.getsize(salida) // 1024} KB). Adjúntalo en el chat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
