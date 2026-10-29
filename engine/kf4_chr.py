#!/usr/bin/env python3
"""
kf4_chr.py - Lee y escribe los modelos de personaje del King's Field IV (chr/cNNNN.chr).

Formato (kfiv-decomp: entity_pool.c, model/model.c, model/model_motion.c, gfx/texture.h):
  cabecera (0x20): 0x04 modelo, 0x08 movimientos, 0x0C texturas, 0x10 modelo propio del hueco, 0x14 / 0x18 sonidos
  modelo (ModelFile): 0x00 tamaño, 0x04 nº de partes, 0x10 32 BoneAnchor (16 bytes), 0x210 partes (16 bytes:
      offset de sus bloques, nº de bloques, hueco 1..3, padre)
  bloque: 0xB0 de cabecera (etiqueta DMA, UNPACK del VIF, dos TEX0, dos etiquetas GIF) y nv vértices de 0x40:
      posición xyz 1, normal xyz + palabra con 0x8000 en los dos primeros de cada tira, s t 1 + "sigue al padre",
      color rgba (128 = normal). length + 1 = 12 + 4 nv, nv <= 30
  movimientos (MotionFile): 0x04 nº, 16 bytes por entrada, luego cada MotionData: tamaño, offset de vectores,
      fotogramas, nº de partes, 16 bytes por parte (nº de claves, -, -, hijo, hermano, -, offset de claves) y
      claves de 0x12 bytes (fotograma, largo, posición, tangentes, giro, tangentes, escala: índices de vectores)
  texturas: tabla (tamaño, nº de entradas, ...) y paquetes GIF de subida (la imagen de 256x256 en 0x3540)
"""

import math
import struct

import numpy as np

VERT = 0x40
CAB = 0xB0
MAX_V = 30


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


class Chr:
    def __init__(self, data):
        self.d = bytes(data)
        d = self.d
        self.cab = list(struct.unpack_from("<8I", d, 0))
        self.m = self.cab[1]
        self.mot = self.cab[2]
        self.tex = self.cab[3]
        m = self.m
        self.n_partes = struct.unpack_from("<H", d, m + 4)[0]
        self.anclas = [(struct.unpack_from("<3f", d, m + 0x10 + 16 * i), d[m + 0x10 + 16 * i + 12])
                       for i in range(32)]
        self.partes = []
        for i in range(self.n_partes):
            off, cnt, hueco, padre = struct.unpack_from("<IHBb", d, m + 0x210 + 16 * i)
            bloques, p = [], m + off
            for _ in range(cnt):
                ln = struct.unpack_from("<H", d, p)[0]
                bloques.append(d[p:p + (ln + 1) * 16])
                p += (ln + 1) * 16
            self.partes.append({"off": off, "hueco": hueco, "padre": padre, "bloques": bloques,
                                "resto": d[m + 0x210 + 16 * i + 8:m + 0x210 + 16 * i + 16]})
        self.movimientos = self._leer_movimientos()

    # ---------------- geometría ----------------
    @staticmethod
    def vertices(bloque):
        nv = u32(bloque, 0x90) & 0x7FFF
        out = []
        for k in range(nv):
            o = CAB + k * VERT
            pos = struct.unpack_from("<3f", bloque, o)
            nrm = struct.unpack_from("<3f", bloque, o + 0x10)
            fl = u32(bloque, o + 0x1C)
            st = struct.unpack_from("<2f", bloque, o + 0x20)
            padre = u32(bloque, o + 0x2C)
            col = struct.unpack_from("<4f", bloque, o + 0x30)
            out.append({"p": pos, "n": nrm, "corte": bool(fl & 0x8000), "st": st, "padre": padre, "col": col})
        return out

    @staticmethod
    def triangulos(vs):
        """Triángulos (índices) de las tiras de un bloque, con el orden del primero de cada tira."""
        tris, ini = [], 0
        for k in range(len(vs)):
            if vs[k]["corte"]:
                if k == 0 or not vs[k - 1]["corte"] or k - 1 != ini:
                    ini = k
                continue
            if k - ini >= 2:
                a, b, c = k - 2, k - 1, k
                tris.append((a, b, c) if (k - ini) % 2 == 0 else (b, a, c))
        return tris

    # ---------------- movimientos ----------------
    def _leer_movimientos(self):
        d, mo = self.d, self.mot
        n = u32(d, mo + 4)
        p = mo + 16 + 16 * n
        out = []
        for _ in range(n):
            size, voff = struct.unpack_from("<II", d, p)
            fc, pc = struct.unpack_from("<HB", d, p + 12)
            partes = []
            for j in range(pc):
                q = p + 16 + 16 * j
                cnt, _, pf, hijo, herm = struct.unpack_from("<5B", d, q)
                ko = u32(d, q + 8)
                claves = []
                for k in range(cnt if ko else 0):
                    claves.append(struct.unpack_from("<9H", d, p + ko + 0x12 * k))
                partes.append({"hijo": hijo, "hermano": herm, "claves": claves})
            nvec = (size - voff) // 12
            vec = [struct.unpack_from("<3f", d, p + voff + 12 * k) for k in range(nvec)]
            out.append({"fotogramas": fc, "partes": partes, "vec": vec, "off": p, "size": size})
            p += size
        return out

    def jerarquia(self, mov=0):
        """padre de cada parte según los enlaces hijo / hermano del movimiento (0 = ninguno, salvo la raíz)."""
        ps = self.movimientos[mov]["partes"]
        padre = [-1] * len(ps)

        def bajar(i):
            h = ps[i]["hijo"]
            while h:
                padre[h] = i
                bajar(h)
                h = ps[h]["hermano"]
        bajar(0)
        return padre

    def pose(self, mov=0, fot=0):
        """Matriz 4x4 (vectores columna) de cada parte en el fotograma fot (sin interpolar: la clave anterior)."""
        M = self.movimientos[mov]
        padre = self.jerarquia(mov)
        loc = []
        for j, pa in enumerate(M["partes"]):
            cl = [c for c in pa["claves"] if c[0] <= fot] or pa["claves"][:1]
            if not cl:
                loc.append(np.eye(4))
                continue
            c = cl[-1]
            pos, rot, esc = M["vec"][c[2]], M["vec"][c[5]], M["vec"][c[8]]
            loc.append(matriz_parte(pos, rot, esc))
        mundo = [None] * len(loc)

        def mm(i):
            if mundo[i] is None:
                mundo[i] = loc[i] if padre[i] < 0 else mm(padre[i]) @ loc[i]
            return mundo[i]
        return [mm(i) for i in range(len(loc))]


def rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1]])


def ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]])


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])


def matriz_parte(pos, rot, esc):
    """ModelMatrix_BuildPartLocal: escala, giro x, z, y, desplazamiento."""
    S = np.diag([esc[0], esc[1], esc[2], 1.0])
    M = ry(rot[1]) @ rz(rot[2]) @ rx(rot[0]) @ S
    M[:3, 3] = pos
    return M


# ---------------- escritura ----------------
def bloque_nuevo(plantilla, verts):
    """Un bloque con la cabecera de plantilla y estos vértices: (pos, normal, corte, st, padre, color)."""
    nv = len(verts)
    assert 0 < nv <= MAX_V
    b = bytearray(plantilla[:CAB]) + bytearray(nv * VERT)
    ln = 12 + 4 * nv - 1
    struct.pack_into("<H", b, 0, ln)
    unp = u32(b, 0x8C)
    struct.pack_into("<I", b, 0x8C, (unp & 0xFF00FFFF) | ((nv * 4 + 2) << 16))
    for o in (0x90, 0xA0):
        w = u32(b, o)
        struct.pack_into("<I", b, o, (w & ~0x7FFF) | nv)
    for k, (p, n, corte, st, padre, col) in enumerate(verts):
        o = CAB + k * VERT
        struct.pack_into("<4f", b, o, p[0], p[1], p[2], 1.0)
        struct.pack_into("<3fI", b, o + 0x10, n[0], n[1], n[2], 0x8000 if corte else 0)
        struct.pack_into("<3fI", b, o + 0x20, st[0], st[1], 1.0, padre)
        struct.pack_into("<4f", b, o + 0x30, *col)
    # la cola: lo que la plantilla lleva tras sus vértices (una palabra de cierre)
    cola = plantilla[CAB + (u32(plantilla, 0x90) & 0x7FFF) * VERT:]
    b += cola[:16].ljust(16, b"\0")
    assert len(b) == (ln + 1) * 16, (len(b), ln)
    return bytes(b)


def modelo_nuevo(chr_base, bloques_por_parte):
    """ModelFile de chr_base con los bloques de cada parte cambiados (lista por parte, [] = sin geometría)."""
    d, m = chr_base.d, chr_base.m
    cab = bytearray(d[m:m + 0x210 + 16 * chr_base.n_partes])
    cuerpo = bytearray()
    base = len(cab)
    base += (-base) % 16
    for i, bl in enumerate(bloques_por_parte):
        off = base + len(cuerpo)
        struct.pack_into("<IH", cab, 0x210 + 16 * i, off, len(bl))
        for b in bl:
            cuerpo += b
    total = bytes(cab).ljust(base, b"\0") + bytes(cuerpo)
    total += bytes((-len(total)) % 16)
    out = bytearray(total)
    struct.pack_into("<I", out, 0, len(out))
    return bytes(out)


def chr_nuevo(chr_base, modelo, texturas=None):
    """El .chr de chr_base con otro modelo (y otras texturas): las demás secciones se desplazan."""
    d = chr_base.d
    c = chr_base.cab
    secciones = sorted({c[1], c[2], c[3], c[4], c[5], c[6], len(d)})
    viejos = {}
    for a, b in zip(secciones, secciones[1:]):
        viejos[a] = d[a:b]
    viejos[c[1]] = modelo
    if texturas is not None:
        viejos[c[3]] = texturas
    out = bytearray(d[:secciones[0]])
    nuevo_off = {}
    for a in secciones[:-1]:
        out += bytes((-len(out)) % 16)
        nuevo_off[a] = len(out)
        out += viejos[a]
    out += bytes((-len(out)) % 16)
    cab = list(c)
    for k in range(1, 7):
        if cab[k] in nuevo_off:
            cab[k] = nuevo_off[cab[k]]
    struct.pack_into("<8I", out, 0, *cab)
    return bytes(out)


# ---------------- texturas ----------------
def subidas(chr_):
    """[(dbp, dbw, dpsm, x, y, w, h, offset de los datos en el .chr, bytes)] de la sección de texturas."""
    d = chr_.d
    t = chr_.tex
    fin = chr_.cab[4] if chr_.cab[4] > t else len(d)
    out = []
    n = u32(d, t + 4)
    for e in range(n):
        p = t + u32(d, t + 16 + 16 * e) + 0x20          # tras la etiqueta DMA y su relleno
        regs = {}
        while p + 16 <= fin:
            lo, hi = struct.unpack_from("<QQ", d, p)
            nloop, flg, nreg = lo & 0x7FFF, (lo >> 58) & 3, (lo >> 60) & 0xF
            eop = (lo >> 15) & 1
            p += 16
            if flg == 0 and nreg == 1 and (hi & 0xF) == 0xE:
                for _ in range(nloop):
                    v, r = struct.unpack_from("<QQ", d, p)
                    regs[r & 0xFF] = v
                    p += 16
            elif flg == 2:
                bb, tr, xy = regs.get(0x50, 0), regs.get(0x52, 0), regs.get(0x51, 0)
                out.append(((bb >> 32) & 0x3FFF, (bb >> 48) & 0x3F, (bb >> 56) & 0x3F,
                            (xy >> 32) & 0x7FF, (xy >> 48) & 0x7FF, tr & 0xFFF, (tr >> 32) & 0xFFF, p, nloop * 16))
                p += nloop * 16
            else:
                break
            if eop and flg == 2 and len(out) >= 2:
                pass
    return out


def textura(chr_):
    """(índices 256x256 o None, paleta 256x4 en orden lógico) de la textura de 8 bits del personaje."""
    ups = subidas(chr_)
    d = chr_.d
    img = pal = None
    for dbp, dbw, dpsm, x, y, w, h, off, nb in ups:
        if dpsm == 0x13 and img is None:
            img = np.frombuffer(d[off:off + w * h], np.uint8).reshape(h, w)
        elif dpsm == 0 and w == 16 and h == 16 and pal is None:
            raw = np.frombuffer(d[off:off + 1024], np.uint8).reshape(256, 4)
            pal = raw[_swap256()]
    return img, pal


def _swap256():
    idx = np.arange(256)
    sw = idx.copy()
    sw[(idx & 0x18) == 0x08] += 8
    sw[(idx & 0x18) == 0x10] -= 8
    return sw


def texturas_nuevas(chr_, img, pal):
    """La sección de texturas con la imagen (256x256 índices) y la paleta (256 x RGBA, alfa 0x80) cambiadas."""
    d = bytearray(chr_.d)
    puesta = {"img": False, "pal": False}
    sub = subidas(chr_)
    # (la gente del IV lleva varias texturas: se cambia la de 256x256 y la paleta que la sigue; plantilla_de elige
    # un bloque que la usa)
    k0 = next((k for k, s_ in enumerate(sub) if s_[2] == 0x13 and (s_[6], s_[5]) == img.shape), 0)
    for dbp, dbw, dpsm, x, y, w, h, off, nb in sub[k0:]:
        if dpsm == 0x13 and not puesta["img"]:
            assert img.shape == (h, w)
            d[off:off + w * h] = np.ascontiguousarray(img, np.uint8).tobytes()
            puesta["img"] = True
        elif dpsm == 0 and w == 16 and h == 16 and not puesta["pal"]:
            raw = np.zeros((256, 4), np.uint8)
            raw[_swap256()] = pal
            d[off:off + 1024] = raw.tobytes()
            puesta["pal"] = True
    assert puesta["img"] and puesta["pal"], puesta
    fin = chr_.cab[4] if chr_.cab[4] > chr_.tex else len(d)
    return bytes(d[chr_.tex:fin])


def plantilla_de(chr_):
    """Un bloque del modelo que pinta con su textura de 256x256 (la que cambia texturas_nuevas)."""
    tbp = next((s_[0] for s_ in subidas(chr_) if s_[2] == 0x13 and (s_[5], s_[6]) == (256, 256)), None)
    primero = None
    for p in chr_.partes:
        for b in p["bloques"]:
            if primero is None:
                primero = b
            for o in range(0, CAB, 16):
                v, r = struct.unpack_from("<QQ", b, o)
                if (r & 0xFF) == 6 and tbp is not None and (v & 0x3FFF) == tbp:
                    return b
    return primero
