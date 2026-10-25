#!/usr/bin/env python3
"""
kf4_texturas.py - Saca de tu ISO de King's Field IV las texturas que usa el Editor de La Torre.

Uso (doble clic en EXPORTAR_TEXTURAS.bat, o):
    python kf4_texturas.py            -> busca la ISO en esta carpeta y crea kf4_texturas/*.png

Luego, en el editor: botón "Texturas del juego" y eliges todos los .png de la carpeta kf4_texturas.
"""

import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kf4_mapdump as md   # noqa: E402
import kf4_tex as kt       # noqa: E402
import kf4_editor as ke    # noqa: E402


def png(img):
    """PNG RGB sin librerías (img: array alto x ancho x 4 de bytes, como el de kf4_tex)."""
    alto, ancho = img.shape[0], img.shape[1]
    rgb = img[:, :, :3].astype("uint8")
    crudo = b"".join(b"\x00" + rgb[y].tobytes() for y in range(alto))

    def trozo(tipo, datos):
        c = tipo + datos
        return struct.pack(">I", len(datos)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(crudo, 6)) + trozo(b"IEND", b""))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        src_path = os.path.abspath(args[0])
    else:
        isos = [f for f in os.listdir(here) if f.lower().endswith(".iso") and "(valle)" not in f]
        isos.sort(key=lambda f: ("(" in f, len(f), f))
        src_path = os.path.join(here, isos[0]) if isos else here
    src = md.Source(src_path)
    d099 = src.read("099.map")
    texs, _, _ = kt.load_map_textures(d099)
    por_clave = {(f["TBP"], f["CBP"]): img for f, img in texs.values()}
    out = os.path.join(here, "kf4_texturas")
    os.makedirs(out, exist_ok=True)
    hechas = 0
    for nombre, clave in ke.TEXTURAS.items():
        img = por_clave.get(clave)
        if img is None:
            print(f"  (no encontré {nombre})")
            continue
        with open(os.path.join(out, nombre + ".png"), "wb") as f:
            f.write(png(img))
        hechas += 1
    print(f"{hechas} texturas guardadas en {out}")


if __name__ == "__main__":
    main()
