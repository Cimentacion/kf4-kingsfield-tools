#!/usr/bin/env python3
"""
kf4_parche.py - Parche suelto para King's Field IV PAL (SLES_509.20) sobre la ISO original de cualquiera,
sin el generador de mapas:
  - la vida en número dentro del orbe
  - en la pantalla de equipo, una fila "Exp" con la barra de experiencia del arma y su nivel
  - las armas suben de nivel antes: a los 70 y 140 golpes (el juego pide 180 y 480)
  - (opcional) mando de dos sticks: izquierdo andar y paso lateral, derecho girar y mirar

No toca los mapas. Escribe una copia "<nombre> (parche).iso" junto a la original; la original no se cambia.

Uso: python kf4_parche.py "King's Field IV.iso" [--sin-hud] [--dos-sticks] [--invertido]
(--sin-hud: sin la vida en número ni la experiencia de armas; solo lo demás que se pida)
"""

import os
import shutil
import struct
import sys

import kf4_mapdump as md
import kf4_valle as v


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    iso = args[0]
    if not os.path.isfile(iso):
        print(f"No encuentro la ISO: {iso}")
        return 1
    mando = "dos_sticks_invertido" if "--invertido" in sys.argv else ("dos_sticks" if "--dos-sticks" in sys.argv
                                                                       else "original")
    log = []
    base, ext = os.path.splitext(iso)
    out = f"{base} (parche){ext}"
    if not (os.path.isfile(out) and os.path.getsize(out) == os.path.getsize(iso)):
        print(f"Copiando la ISO -> {os.path.basename(out)} (tarda un poco)...")
        shutil.copyfile(iso, out)
    # el ejecutable, siempre desde el original
    s0 = md.Source(iso)
    exe = next((k for k in s0.iso_files if k.startswith(("SLES_", "SLUS_", "SCES_", "SLPS_"))), None)
    if exe != "SLES_509.20":
        print(f"AVISO: el ejecutable es {exe}, no el SLES_509.20 (PAL) para el que está hecho el parche")
    if not exe:
        print("No encuentro el ejecutable en la ISO")
        return 1
    off, size = s0.iso_files[exe]
    with open(iso, "rb") as f:
        f.seek(off)
        elf = f.read(size)
    hud = "--sin-hud" not in sys.argv
    if not hud and mando == "original":
        print("Nothing to patch / Nada que parchear")
        return 0
    nuevo = v.parchear_ejecutable(elf, 1.0, log, mando=mando, vida_numero=hud, cruz=False, exp_menu=hud,
                                  cruz_off=None, escalon=False)
    with open(out, "r+b") as f:
        f.seek(off)
        f.write(nuevo)
    # por idioma: la página del arma con la fila de experiencia y, si se pide, el daño de los enemigos
    idiomas = 0
    for lang in ("SPA", "ENG", "FRA", "GER", "ITA"):
        dat_off, tab = v._dat_table(iso, lang)
        if not tab:
            continue
        idiomas += 1
        _, d_a = v._leer_dat(iso, lang, "menu/equip_a_para.dat")
        _, d_o = v._leer_dat(iso, lang, "menu/option_para.dat")
        ent = tab.get("menu/equip_a_para.dat")
        if hud and ent and d_a and d_o:
            para = v.para_arma_con_exp(d_a, d_o)
            if para is None:
                log.append(f"AVISO {lang}: equip_a_para.dat no es el que conozco; sin fila de experiencia")
            elif len(para) > ent[2]:
                log.append(f"AVISO {lang}: la página del arma no cabe en su sitio del DAT")
            else:
                with open(out, "r+b") as f:
                    f.seek(dat_off + ent[3])
                    f.write(para + bytes(ent[2] - len(para)))
                    f.seek(ent[0] + 0x34)
                    f.write(struct.pack("<I", len(para)))
    log.append(f"Idiomas parcheados: {idiomas}")
    log.append(f"ISO parcheada: {out}")
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
