#!/usr/bin/env python3
"""
kf2_extraer.py - Saca los archivos de datos de un King's Field de PS1 (imagen .bin/.cue) a kf2_datos.zip,
para estudiar sus mapas. Lee el disco directamente (ISO 9660 dentro de sectores de 2352 bytes) y mete:
  - lista.txt con todos los archivos del disco y su tamaño
  - SYSTEM.CNF y el ejecutable (para saber qué versión es)
  - los archivos de datos, del más pequeño al más grande, hasta 60 MB
    (sin vídeos .STR ni audio .XA/.DA/.VAG, que no hacen falta)

Uso: python kf2_extraer.py "ruta\\al\\juego.cue"   (o el .bin, o la carpeta que los tiene)
"""

import os
import struct
import sys
import zipfile

LIMITE = 60 * 1024 * 1024
SALTAR = (".STR", ".XA", ".DA", ".VAG", ".VB", ".MOV")


def buscar_bin(ruta):
    if os.path.isdir(ruta):
        for nombre in sorted(os.listdir(ruta)):
            if nombre.lower().endswith(".cue"):
                return buscar_bin(os.path.join(ruta, nombre))
        for nombre in sorted(os.listdir(ruta), key=lambda n: -os.path.getsize(os.path.join(ruta, n))):
            if nombre.lower().endswith((".bin", ".img", ".iso")):
                return os.path.join(ruta, nombre)
        return None
    if ruta.lower().endswith(".cue"):
        carpeta = os.path.dirname(ruta)
        with open(ruta, "r", errors="replace") as f:
            for linea in f:
                linea = linea.strip()
                if linea.upper().startswith("FILE"):
                    nombre = linea[linea.index('"') + 1:linea.rindex('"')] if '"' in linea else linea.split()[1]
                    candidato = os.path.join(carpeta, nombre)
                    if os.path.isfile(candidato):
                        return candidato
        return buscar_bin(carpeta)
    return ruta if os.path.isfile(ruta) else None


class Disco:
    def __init__(self, ruta):
        self.f = open(ruta, "rb")
        tam = os.path.getsize(ruta)
        cab = self.f.read(16)
        if cab[:12] == b"\x00" + b"\xff" * 10 + b"\x00":
            self.sector = 2352
            self.datos = 24 if cab[15] == 2 else 16
        else:
            self.sector, self.datos = 2048, 0
        self.n = tam // self.sector

    def leer_sector(self, lba):
        self.f.seek(lba * self.sector + self.datos)
        return self.f.read(2048)

    def leer(self, lba, tam):
        out = bytearray()
        while len(out) < tam:
            out += self.leer_sector(lba)
            lba += 1
        return bytes(out[:tam])

    def archivos(self):
        pvd = self.leer_sector(16)
        if pvd[1:6] != b"CD001":
            raise RuntimeError("No encuentro el sistema de archivos ISO 9660 en la imagen")
        raiz = pvd[156:156 + 34]
        out = []
        self._dir(struct.unpack_from("<I", raiz, 2)[0], struct.unpack_from("<I", raiz, 10)[0], "", out, set())
        return out

    def _dir(self, lba, tam, ruta, out, vistos):
        if lba in vistos:
            return
        vistos.add(lba)
        datos = self.leer(lba, tam)
        i = 0
        while i < len(datos):
            n = datos[i]
            if n == 0:
                i = (i // 2048 + 1) * 2048
                continue
            reg = datos[i:i + n]
            l_lba, l_tam = struct.unpack_from("<I", reg, 2)[0], struct.unpack_from("<I", reg, 10)[0]
            flags, ln = reg[25], reg[32]
            nombre = reg[33:33 + ln]
            i += n
            if nombre in (b"\x00", b"\x01"):
                continue
            nombre = nombre.decode("ascii", "replace").split(";")[0]
            completo = f"{ruta}/{nombre}" if ruta else nombre
            if flags & 2:
                self._dir(l_lba, l_tam, completo, out, vistos)
            else:
                out.append((completo, l_lba, l_tam))


def main():
    aqui = os.path.dirname(os.path.abspath(__file__))
    if len(sys.argv) > 1:
        ruta = sys.argv[1]
    else:
        ruta = os.path.join(os.path.expanduser("~"), "Downloads", "King's Field II")
        for carpeta in ("King's Field (Europe)", "King's Field (USA)", "King's Field", "King's Field II"):
            cand = os.path.join(os.path.expanduser("~"), "Downloads", carpeta)
            if os.path.isdir(cand):
                ruta = cand
                break
    binario = buscar_bin(ruta)
    if not binario:
        print(f"No encuentro el .bin del juego en: {ruta}")
        print("Arrastra el .cue (o el .bin) encima de EXTRAER_KF2.bat.")
        return 1
    print(f"Leyendo {binario}")
    disco = Disco(binario)
    lista = disco.archivos()
    print(f"{len(lista)} archivos en el disco")
    salida = os.path.join(aqui, "kf2_datos.zip")
    total = 0
    metidos, saltados = [], []
    lineas = [f"{nombre}\t{tam}\tlba {lba}" for nombre, lba, tam in lista]
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("lista.txt", "\n".join(lineas) + "\n")
        prioridad = [x for x in lista if x[0].upper().startswith(("SYSTEM.CNF", "SLUS", "SLPS", "SCES", "SLES", "SCUS", "PSX.EXE"))]
        # luego los archivos .T y los ejecutables (ahí están mapas, modelos y texturas), y después lo demás
        datos = sorted((x for x in lista if x not in prioridad and x[0].upper().endswith((".T", ".EXE", ".BIN", ".DAT"))),
                       key=lambda x: x[2])
        resto = datos + sorted((x for x in lista if x not in prioridad and x not in datos), key=lambda x: x[2])
        for nombre, lba, tam in prioridad + resto:
            if nombre.upper().endswith(SALTAR) or (total + tam > LIMITE and nombre not in [p[0] for p in prioridad]):
                saltados.append(nombre)
                continue
            z.writestr(nombre, disco.leer(lba, tam))
            total += tam
            metidos.append(nombre)
    print(f"Metidos {len(metidos)} archivos ({total // 1024} KB); fuera {len(saltados)}: {', '.join(saltados[:20])}"
          + (" ..." if len(saltados) > 20 else ""))
    print(f"Hecho: {salida}  ({os.path.getsize(salida) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
