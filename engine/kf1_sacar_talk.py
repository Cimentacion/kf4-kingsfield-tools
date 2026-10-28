#!/usr/bin/env python3
"""Saca del disco de King's Field (europeo, el .bin o .cue) los diálogos (CD/COM/TALK0.T, TALK1.T, TALK2.T: uno por
idioma, en imágenes) y los mete en kf1_talk.zip junto a este script, para mandármelo. No necesita nada más.

Uso: python kf1_sacar_talk.py ["carpeta, .bin o .cue del King's Field"]
     (sin nada: la carpeta del script si tiene el .bin; si no, Descargas/King's Field (Europe))
"""
import os
import struct
import sys
import zipfile


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
    if len(sys.argv) > 1 and sys.argv[1].strip():
        ruta = sys.argv[1]
    elif any(n.lower().endswith((".bin", ".cue")) for n in os.listdir(aqui)):
        ruta = aqui
    else:
        ruta = os.path.join(os.path.expanduser("~"), "Downloads", "King's Field (Europe)")
    binario = buscar_bin(ruta)
    if not binario:
        print(f"No encuentro el .bin del King's Field en {ruta}")
        return 1
    print(f"Disco: {binario}")
    disco = Disco(binario)
    salida = os.path.join(aqui, "kf1_talk.zip")
    elegidos = [(n, l, t) for n, l, t in disco.archivos() if os.path.basename(n).upper().startswith(("TALK", "STALK"))]
    if not elegidos:
        print("Ese disco no tiene TALK*.T")
        return 1
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, lba, tam in elegidos:
            z.writestr(nombre.lstrip("/"), disco.leer(lba, tam))
            print(f"  {nombre} ({tam // 1024} KB)")
    print(f"Listo: {salida} ({os.path.getsize(salida) // 1024} KB). Mándamelo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
