#!/usr/bin/env python3
"""
kf4_extraer_chr.py - Saca los enemigos del KF4 (chr/*.chr) y su tabla (param/chr.prm) de tu ISO a un zip, para
estudiar su formato (el modelo con huesos, sus movimientos) y poder meter enemigos del King's Field.

Uso: python kf4_extraer_chr.py "King's Field IV.iso"     (o EXTRAER_CHR.bat)
Escribe chr_kf4.zip junto a la ISO. No cambia la ISO.
"""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kf4_mapdump as md  # noqa: E402

# los que hacen falta primero: la tabla, la serpiente y la planta (los que se pondrían de base para el pulpo) y
# unos cuantos pequeños de muestra; con --todos, todos
PRIMERO = ("param/chr.prm",)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    aqui = os.path.dirname(os.path.abspath(__file__))
    iso = args[0] if args else None
    if not iso:
        for carpeta in (aqui, os.path.dirname(aqui)):
            isos = [f for f in os.listdir(carpeta) if f.lower().endswith(".iso") and "(" not in f]
            if isos:
                iso = os.path.join(carpeta, isos[0])
                break
    if not iso or not os.path.isfile(iso):
        print("No encuentro la ISO de King's Field IV. Arrástrala encima de EXTRAER_CHR.bat.")
        return 1
    src = md.Source(iso)
    todos = sorted(src.names)
    nombres = [n for n in todos if "chr" in n or n.startswith("param/") or n in PRIMERO]
    if not nombres:
        print("No encuentro chr/ en la ISO (¿es la PAL SLES-50920?)")
        return 1
    out = os.path.join(os.path.dirname(os.path.abspath(iso)), "chr_kf4.zip")
    total = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        lista = []
        for n in todos:
            v = src.names[n]
            lista.append(f"{n}\t{v[1] if isinstance(v, tuple) else os.path.getsize(v)}")
        z.writestr("lista_archivos.txt", "\r\n".join(lista))
        for n in nombres:
            d = src.read(n)
            if not d:
                continue
            if "--todos" not in sys.argv and n.startswith("chr/") and len(d) > 3_000_000:
                continue                       # los jefes enormes, de momento no
            z.writestr(n, d)
            total += len(d)
    print(f"{len(nombres)} archivos ({total // 1024} KB sin comprimir) -> {out}")
    print(f"Tamaño del zip: {max(1, os.path.getsize(out) // 1024)} KB. Mándamelo en el chat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
