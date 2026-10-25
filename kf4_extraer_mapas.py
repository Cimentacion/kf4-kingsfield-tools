#!/usr/bin/env python3
"""kf4_extraer_mapas.py - Saca de la ISO de King's Field IV unos mapas a kf4_mapas_cielo.zip (para buscar el
cielo nublado y otros recursos: enemigos, cofres, puertas). Uso: python kf4_extraer_mapas.py [ISO] [mapas...]"""
import os
import sys
import zipfile

import kf4_mapdump as md

# exteriores con cielo (Ancient City Exterior, Old Battlefield, Ocean Shore, East Valley, Mansion exterior)
# y unos con cofres, puertas y paredes que se mueven
MAPAS = ["012", "037", "027", "004", "033", "000", "002", "011", "008", "013"]


def main():
    aqui = os.path.dirname(os.path.abspath(__file__))
    args = [a for a in sys.argv[1:]]
    iso = next((a for a in args if a.lower().endswith(".iso")), None)
    if iso is None:
        isos = sorted(f for f in os.listdir(aqui) if f.lower().endswith(".iso") and "(valle)" not in f)
        iso = os.path.join(aqui, isos[0]) if isos else None
    if not iso:
        print("No encuentro la ISO de King's Field IV en esta carpeta")
        return 1
    mapas = [a for a in args if not a.lower().endswith(".iso")] or MAPAS
    src = md.Source(iso)
    salida = os.path.join(aqui, "kf4_mapas_cielo.zip")
    total = 0
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for m in mapas:
            nombre = f"{m}.map"
            try:
                d = src.read(nombre)
            except Exception as e:
                print(f"{nombre}: no está ({e})")
                continue
            z.writestr(nombre, d)
            total += len(d)
            print(f"{nombre}: {len(d) // 1024} KB")
    print(f"Hecho: {salida} ({os.path.getsize(salida) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
