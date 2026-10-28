#!/usr/bin/env python3
"""Saca del disco de King's Field (europeo, el .cue/.bin) los diálogos (CD/COM/TALK0.T, TALK1.T, TALK2.T: uno por
idioma, en imágenes) y los mete en kf1_talk.zip junto a este script, para mandármelo.

Uso: python kf1_sacar_talk.py "carpeta o .cue del King's Field"
"""
import os
import sys
import zipfile

import kf2_extraer as kx


def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "Downloads", "King's Field (Europe)")
    binario = kx.buscar_bin(ruta)
    if not binario:
        print(f"No encuentro el .bin del King's Field en {ruta}")
        return 1
    disco = kx.Disco(binario)
    salida = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kf1_talk.zip")
    n = 0
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, lba, tam in disco.archivos():
            if os.path.basename(nombre).upper().startswith(("TALK", "STALK")):
                z.writestr(nombre.lstrip("/"), disco.leer(lba, tam))
                print(f"  {nombre} ({tam // 1024} KB)")
                n += 1
    if not n:
        print("Ese disco no tiene TALK*.T")
        return 1
    print(f"Listo: {salida}  (mándamelo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
