#!/usr/bin/env python3
"""
kf4_caracol.py - El caracol gigante del King's Field (MO.T[16]) como enemigo del King's Field IV.

Igual que el pulpo (kf4_pulpo): su modelo del PS1 con un esqueleto puesto a mano (el pie, la concha y el cuello
en tres trozos hasta la cabeza y los cuernos) y movimientos escritos aquí. Se porta como la babosa del IV
(registro 2, tipo 1: se arrastra hacia ti y muerde de cerca); el arrastrarse mueve al bicho con el propio
movimiento (la parte raíz avanza, como en la babosa).

  caracol_chr(babosa, mo_t, vram) -> bytes del .chr nuevo
  caracol_prm(registro_babosa)    -> registro de chr.prm
"""

import math
import struct

import numpy as np

import kf2_tex
import kf4_chr as kc
import kf4_pulpo as kp

MODELO = 79                  # chr/c0079.chr: archivo vacío de 32 bytes en el IV (nadie lo usa)
REGISTRO = 63                # chr.prm 63: vacío en el IV
REGISTRO_BASE = 2            # la babosa
MO_CARACOL = 16
ESC = 250.0 / 2048 * 0.75    # PS1 -> cm del IV (el original mide 2,8 m de largo: algo más pequeño)
CLUT_CONCHA = 31456

# partes: 0 raíz, 1 pie, 2 concha, 3 cuello, 4 cabeza, 5 cuernos
PADRE = [-1, 0, 1, 1, 3, 4]
CORTES_CUELLO = (-500, -1300, -2000)      # z (PS1): delante del pie empieza el cuello; luego cabeza y cuernos
FOT = {"quieto": 120, "arrastrar": 135, "golpeado": 20, "golpe_fuerte": 30, "muerte": 90, "mordisco": 40}
ORDEN_MOV = ["quieto", "arrastrar", "golpeado", "golpe_fuerte", "muerte", "mordisco"]
# animación del IV -> movimiento (chr.prm 0x60): 0 quieto, 3 andar, 14 / 15 golpes, 16 muerte, 20 el mordisco
ANIMACION = {0: 0, 3: 1, 13: 0, 14: 2, 15: 3, 16: 4, 20: 5}
AVANCE = 70.0                # unidades del IV que avanza en un ciclo de arrastrarse (la babosa, 30)


def malla(mo_t):
    d = mo_t[MO_CARACOL]
    t = struct.unpack_from("<I", d, 8)[0]
    vs, prims = kf2_tex.objetos_tmd(d[t:], por_8=False)[0]
    return [tuple(float(c) for c in v) for v in vs], prims


def _dueno(v, de_concha):
    x, y, z = v
    if de_concha:
        return 2
    if z > CORTES_CUELLO[0]:
        return 1
    if z > CORTES_CUELLO[1]:
        return 3
    if z > CORTES_CUELLO[2]:
        return 4
    return 5


def _prof(p):
    n = 0
    while p > 1:
        p = PADRE[p]
        n += 1
    return n


def rig(vs, prims):
    concha = set()
    for tp, cl, uvs, refs, _ in prims:
        if cl == CLUT_CONCHA:
            concha.update(refs)
    duenos = [_dueno(v, i in concha) for i, v in enumerate(vs)]
    tris = []
    for tp, cl, uvs, refs, _ in prims:
        orden = [(0, 1, 2), (1, 3, 2)] if len(refs) == 4 else [(0, 1, 2)]
        for o in orden:
            tris.append(((tp, cl), [refs[j] for j in o], [uvs[j] for j in o]))
    for _ in range(50):          # cada triángulo: vértices de una parte o de su padre
        cambio = False
        for _, refs, _ in tris:
            ps = {duenos[r] for r in refs}
            if len(ps) == 1:
                continue
            D = max(ps, key=_prof)
            for r in refs:
                q = duenos[r]
                if q != D and q != PADRE[D]:
                    a = max((q, D), key=_prof)
                    for r2 in refs:
                        if duenos[r2] == a:
                            duenos[r2] = PADRE[a]
                    cambio = True
                    break
        if not cambio:
            break
    V = np.array(vs)
    piv = [np.zeros(3) for _ in PADRE]
    for p in range(1, len(PADRE)):
        propios = V[[i for i in range(len(vs)) if duenos[i] == p]]
        if len(propios) == 0:
            piv[p] = piv[PADRE[p]].copy()
        elif p == 1:
            piv[p] = np.array([0.0, 0.0, 0.0])
        elif p == 2:
            piv[p] = np.array([0.0, -400.0, 400.0])          # la base de la concha
        else:
            zmax = propios[:, 2].max()                      # donde empieza ese trozo (hacia atrás)
            cerca = propios[propios[:, 2] > zmax - 250]
            piv[p] = cerca.mean(0)
    return duenos, piv, tris


def _campana(t, a, b, c):
    return kp._campana(t, a, b, c)


def _pose(nombre, f, total):
    """{parte: (giro x, giro y, giro z)}, desplazamiento de la raíz (z) y del pie (y)."""
    t = f / max(1, total)
    w = 2 * math.pi * t
    g = {p: (0.0, 0.0, 0.0) for p in range(len(PADRE))}
    raiz_z, pie_y = 0.0, 0.0
    if nombre == "quieto":
        g[3] = (0.05 * math.sin(w), 0.10 * math.sin(w * 0.5), 0.0)
        g[4] = (0.06 * math.sin(w + 1), 0.06 * math.sin(w * 0.5 + 1), 0.0)
        g[5] = (0.10 * math.sin(w * 2), 0.0, 0.0)
        g[2] = (0.0, 0.0, 0.015 * math.sin(w))
    elif nombre == "arrastrar":
        raiz_z = -AVANCE * t
        ola = math.sin(w * 2)
        pie_y = 3.0 * ola
        g[2] = (0.02 * ola, 0.0, 0.02 * math.sin(w))
        g[3] = (0.06 * math.sin(w * 2 + 0.8), 0.12 * math.sin(w), 0.0)
        g[4] = (0.05 * math.sin(w * 2 + 1.6), 0.08 * math.sin(w + 0.7), 0.0)
        g[5] = (0.10 * math.sin(w * 2 + 2.4), 0.0, 0.0)
    elif nombre in ("golpeado", "golpe_fuerte"):
        e = math.sin(math.pi * t) * (1.6 if nombre == "golpe_fuerte" else 1.0)
        g[3] = (-0.30 * e, 0.0, 0.0)           # el cuello se encoge hacia atrás
        g[4] = (-0.25 * e, 0.0, 0.0)
        g[5] = (0.30 * e, 0.0, 0.0)
        g[2] = (0.05 * e, 0.0, 0.0)
    elif nombre == "muerte":
        e = min(1.0, t * 1.5)
        g[3] = (0.45 * e, 0.0, 0.15 * e)       # el cuello cae al suelo
        g[4] = (0.35 * e, 0.0, 0.0)
        g[5] = (0.40 * e, 0.0, 0.0)
        g[2] = (0.0, 0.0, 0.25 * e)            # la concha se ladea
        pie_y = 6.0 * e
    else:                                       # mordisco: echa la cabeza atrás y la lanza, golpe hacia el 22
        atras = _campana(t, 0.0, 0.35, 0.5)
        golpe = _campana(t, 0.38, 0.55, 0.9)
        g[3] = (-0.35 * atras + 0.30 * golpe, 0.0, 0.0)
        g[4] = (-0.30 * atras + 0.45 * golpe, 0.0, 0.0)
        g[5] = (0.20 * atras - 0.20 * golpe, 0.0, 0.0)
        raiz_z = -25.0 * golpe
    return g, raiz_z, pie_y


def _movimiento(piv, nombre, total, paso=5):
    fots = list(range(0, total, paso)) + [total]
    vec, idx = [], {}

    def v(x):
        x = tuple(round(float(c), 5) for c in x)
        if x not in idx:
            idx[x] = len(vec)
            vec.append(x)
        return idx[x]
    v((0, 0, 0))
    uno = v((1, 1, 1))
    curvas = []
    for f in fots:
        g, rz, py = _pose(nombre, f, total)
        fila = []
        for p in range(len(PADRE)):
            if p == 0:
                pos = (0.0, 0.0, rz)
            elif p == 1:
                pos = (0.0, py, 0.0)
            else:
                pos = tuple((piv[p] - piv[PADRE[p]]) * ESC)
            fila.append((pos, g[p]))
        curvas.append(fila)
    n = len(PADRE)
    partes = []
    for p in range(n):
        claves = []
        for j, f in enumerate(fots):
            pos, rot = curvas[j][p]
            a = curvas[max(0, j - 1)][p]
            b = curvas[min(len(fots) - 1, j + 1)][p]
            k = 0.5 if 0 < j < len(fots) - 1 else 0.0
            tp = tuple((np.array(b[0]) - np.array(a[0])) * k)
            tr = tuple((np.array(b[1]) - np.array(a[1])) * k)
            largo = (fots[j + 1] - f) if j + 1 < len(fots) else 0
            claves.append((f, largo, v(pos), v(tp), v(tp), v(rot), v(tr), v(tr), uno))
        partes.append(claves)
    hijos = {p: [q for q in range(n) if PADRE[q] == p] for p in range(n)}
    hermano = {}
    for p, hs in hijos.items():
        for a, b in zip(hs, hs[1:]):
            hermano[a] = b
    out = bytearray(16 + 16 * n)
    offs = []
    for claves in partes:
        offs.append(len(out))
        for c in claves:
            out += struct.pack("<9H", *c)
    out += bytes((-len(out)) % 16)
    voff = len(out)
    for x in vec:
        out += struct.pack("<3f", *x)
    out += bytes((-len(out)) % 16)
    struct.pack_into("<IIIHBB", out, 0, len(out), voff, 0, total, n, 0)
    for p in range(n):
        struct.pack_into("<BBBBBBBBII", out, 16 + 16 * p, len(partes[p]), 0, p, hijos[p][0] if hijos[p] else 0,
                         hermano.get(p, 0), 0, 0, 0, offs[p], 0)
    return bytes(out)


def _archivo_movimientos(piv):
    movs = [_movimiento(piv, nm, FOT[nm]) for nm in ORDEN_MOV]
    out = bytearray(16 + 16 * len(movs))
    off, pos = len(out), []
    for m in movs:
        pos.append(off)
        off += len(m)
    struct.pack_into("<IIII", out, 0, off, len(movs), 0, 0)
    for k in range(1, len(movs)):
        struct.pack_into("<II", out, 16 + 16 * k, k - 1, pos[k - 1])
    for m in movs:
        out += m
    return bytes(out)


def caracol_chr(base, mo_t, vram):
    """base: kc.Chr de la babosa (c0002)."""
    vs, prims = malla(mo_t)
    duenos, piv, tris = rig(vs, prims)
    img, pal, sitio = kp.textura(vram, tris)
    V = np.array(vs)
    nrm = np.zeros_like(V)
    for _, refs, _ in tris:
        a, b, c = V[refs[0]], V[refs[1]], V[refs[2]]
        nrm[refs] += np.cross(b - a, c - a)
    nrm /= np.maximum(1e-9, np.linalg.norm(nrm, axis=1))[:, None]
    nrm = -nrm
    plantilla = base.partes[[i for i, p in enumerate(base.partes) if p["bloques"]][0]]["bloques"][0]
    por_parte = [[] for _ in PADRE]
    for clave, refs, uvs in tris:
        ps = {duenos[r] for r in refs}
        D = next(p for p in ps if all(q == p or q == PADRE[p] for q in ps))
        dx, dy = sitio[clave]
        tri = []
        for r, (u, v) in zip(refs, uvs):
            sobre_padre = duenos[r] != D
            origen = piv[PADRE[D]] if sobre_padre else piv[D]
            p = (V[r] - origen) * ESC
            E = kp.TEX_ESCALA
            tri.append((tuple(p), tuple(nrm[r]), kp._sombra(V[r], nrm[r]),
                        ((u * E + dx + E / 2) / 256.0, (v * E + dy + E / 2) / 256.0), 1 if sobre_padre else 0))
        por_parte[D].append(tri)
    bloques = []
    for p in range(len(PADRE)):
        bl, ts = [], por_parte[p]
        for i in range(0, len(ts), kp.MAX_TRIS):
            verts = []
            for tri in ts[i:i + kp.MAX_TRIS]:
                for k, (pos, n, col, st, sp) in enumerate([tri[0], tri[2], tri[1]]):
                    verts.append((pos, n, k < 2, st, sp, col))
            bl.append(kc.bloque_nuevo(plantilla, verts))
        bloques.append(bl)
    n = len(PADRE)
    cab = bytearray(0x210 + 16 * n)
    struct.pack_into("<IH", cab, 0, 0, n)
    boca = (np.array([0.0, -900.0, -2300.0]) - piv[4]) * ESC
    for k in range(32):
        if k < 2:
            struct.pack_into("<3fB", cab, 0x10 + 16 * k, boca[0], boca[1], boca[2], 4)
        else:
            struct.pack_into("<3fB", cab, 0x10 + 16 * k, 0, 0, 0, 0xFF)
    cuerpo = bytearray()
    base_off = len(cab) + (-len(cab)) % 16
    for p in range(n):
        struct.pack_into("<IHBb", cab, 0x210 + 16 * p, base_off + len(cuerpo), len(bloques[p]), 1 if p == 0 else 0,
                         PADRE[p])
        for b in bloques[p]:
            cuerpo += b
    modelo = bytearray(bytes(cab).ljust(base_off, b"\0") + cuerpo)
    modelo += bytes((-len(modelo)) % 16)
    struct.pack_into("<I", modelo, 0, len(modelo))
    return kp.chr_con(base, bytes(modelo), _archivo_movimientos(piv), kc.texturas_nuevas(base, img, pal))


def caracol_prm(base_rec):
    r = bytearray(base_rec)
    struct.pack_into("<H", r, 0, MODELO)
    struct.pack_into("<H", r, 0x0A, 75)            # vida: 300 en el King's Field, a la cuarta parte como lo demás
    struct.pack_into("<H", r, 0x0E, 16)            # experiencia: la del King's Field
    struct.pack_into("<HH", r, 0x06, 110, 120)     # radio y alto contra el mapa
    struct.pack_into("<H", r, 0xEE, 150)
    struct.pack_into("<H", r, 0xCC, 130)
    r[0xD2] = 100
    ids = [0] * 0x20
    for a, m in ANIMACION.items():
        ids[a] = m
    r[0x60:0x80] = bytes(ids)
    # el mordisco: el de la babosa, en la ventana del movimiento nuevo y con más alcance
    o = 0x240
    r[o + 1] = 18                                   # se encara contigo hasta el fotograma 18
    r[o + 3] = 0                                    # (con 26 el mordisco no salía: como en la babosa)
    struct.pack_into("<HHf", r, o + 4, 0, 200, math.pi / 2)
    h = o + 0x10
    struct.pack_into("<9h", r, h, 0, 14, 0, 0, 0, 0, 6, 0, 0)
    struct.pack_into("<HHHH", r, h + 0x20, 140, 60, 20, 26)
    # la babosa del IV se dibuja semitransparente (bit 0x40 del byte 0x11, solo lo llevan las babosas 2, 3 y el 27):
    # el caracol es macizo
    r[0x11] &= ~0x40
    return bytes(r)
