#!/usr/bin/env python3
"""
kf4_pulpo.py - El Kraken (el pulpo) del King's Field como enemigo del King's Field IV.

Su modelo es el de MO.T[29] del King's Field (un TMD de 202 vértices). El King's Field lo anima moviendo
vértices; el IV anima huesos, así que aquí se le pone un esqueleto: el cuerpo, seis patas de tres trozos y los dos
brazos largos de cuatro, y se le escriben sus movimientos (respirar, recibir un golpe, morir, el chorro de tinta
y el latigazo con los brazos). El comportamiento es el de la Flor oscura del IV (tipo 71: se queda en su sitio,
escupe a distancia), con un golpe cuerpo a cuerpo añadido.

Lo que sale:
  pulpo_chr(chr_flor, mo_t, vram_kf1)  -> bytes del chr/c0037.chr nuevo
  pulpo_prm(registro_flor)             -> registro de chr.prm (0x450 bytes) del pulpo
"""

import math
import struct

import numpy as np

import kf2_tex
import kf4_chr as kc

MODELO_PULPO = 37            # chr/c0037.chr: en el IV es un archivo vacío de 32 bytes que nadie usa (el registro
                             # 37 usa el modelo 36); se le cambia el sitio en la tabla del DAT y el nombre no cambia
REGISTRO_PULPO = 48          # chr.prm 48: registro vacío en el IV
REGISTRO_BASE = 2            # la babosa: su IA (se acerca y ataca de cerca), como el caracol. La de la Flor
                             # oscura (49) era una torreta sin cuerpo a cuerpo: nunca daba latigazos
ESC = 250.0 / 2048           # unidades del PS1 -> cm del IV, a la escala del grande (la clase 0 del nivel 0, escala 1)
MINI = 65                    # chr.prm 65 (vacío en el IV): los pulpitos, el mismo modelo a la escala de su clase
MINI_ESCALA = 38             # % (clases 18, 27 y 29 del nivel 0: escala 1536 / 4096)
MO_CAPUCHA = 30              # la capucha (el cuerpo de arriba): en el original es otro bicho en la misma casilla
CAPUCHA_BAJO = -900          # y (PS1) donde queda el borde de abajo de la capucha: tapa el cuerpo, salen las patas

R_CUERPO = 700               # unidades del PS1: lo que está más cerca del eje es cuerpo
PATAS = [0, 32, 147, 180, -147, -32]       # acimut de cada pata (grados, atan2(z, x))
BRAZOS = [28, 152]
CORTES_PATA = [700, 1300, 2000]
CORTES_BRAZO = [700, 1600, 2700, 3800]
# el eje de los brazos en (radio, altura): de donde salen del cuerpo a la punta
EJE_BRAZO = [(700, 1800), (1400, 1300), (2000, 1850), (2600, 2900), (2950, 4000), (2975, 5233)]

FOT = {"quieto": 120, "golpeado": 30, "golpe_fuerte": 50, "muerte": 60, "tinta": 60, "latigo": 50, "arrastrar": 90}
AVANCE = 120.0               # unidades del IV que avanza en un ciclo de arrastrarse (lo que mueve al bicho)


def _ang(a, b):
    return abs((a - b + 180) % 360 - 180)


def _s_brazo(r, h):
    """posición a lo largo del eje del brazo (unidades del PS1)."""
    mejor, acum, s_mejor = 1e18, 0.0, 0.0
    for (r0, h0), (r1, h1) in zip(EJE_BRAZO, EJE_BRAZO[1:]):
        dx, dy = r1 - r0, h1 - h0
        L = math.hypot(dx, dy)
        t = max(0.0, min(1.0, ((r - r0) * dx + (h - h0) * dy) / (L * L)))
        px, py = r0 + t * dx, h0 + t * dy
        dd = math.hypot(r - px, h - py)
        if dd < mejor:
            mejor, s_mejor = dd, acum + t * L
        acum += L
    return s_mejor + EJE_BRAZO[0][0]


class Esqueleto:
    """Partes: 0 raíz, 1 cuerpo, luego cada pata (3) y cada brazo (4), en cadena."""

    def __init__(self):
        self.padre = [-1, 0]
        self.miembro = [None, None]       # (tipo, índice, trozo)
        self.cadenas = []
        for tipo, dirs, cortes in (("pata", PATAS, CORTES_PATA), ("brazo", BRAZOS, CORTES_BRAZO)):
            for i, _ in enumerate(dirs):
                cad = []
                for k in range(len(cortes)):
                    self.padre.append(1 if k == 0 else cad[-1])
                    self.miembro.append((tipo, i, k))
                    cad.append(len(self.padre) - 1)
                self.cadenas.append((tipo, i, cad))
        self.n = len(self.padre)

    def parte(self, tipo, i, k):
        for t, j, cad in self.cadenas:
            if t == tipo and j == i:
                return cad[k]

    def hijos(self, p):
        return [q for q in range(self.n) if self.padre[q] == p]


def _dueno(esq, v):
    x, y, z = v
    h, r, az = -y, math.hypot(x, z), math.degrees(math.atan2(z, x))
    if r < R_CUERPO:
        return 1, 0.0
    brazo = min(range(len(BRAZOS)), key=lambda i: _ang(az, BRAZOS[i]))
    if _ang(az, BRAZOS[brazo]) < 20 and h > 1250 + max(0, 1400 - r) * 0.4 and r > 1000:
        s = _s_brazo(r, h)
        k = max(i for i, c in enumerate(CORTES_BRAZO) if s >= c - 1e-6) if s >= CORTES_BRAZO[0] else 0
        return esq.parte("brazo", brazo, k), s
    if h > 1300:                       # la cara y los ojos: cuerpo
        return 1, 0.0
    pata = min(range(len(PATAS)), key=lambda i: _ang(az, PATAS[i]))
    k = max(i for i, c in enumerate(CORTES_PATA) if r >= c)
    return esq.parte("pata", pata, k), r


def malla_kf1(mo_t, capucha=True):
    """(vértices, prims, índice desde el que van los de la capucha): las patas (MO.T[29]) y encima la capucha
    (MO.T[30]), que en el King's Field es otro enemigo puesto en la misma casilla."""
    d = mo_t[29]
    t = struct.unpack_from("<I", d, 8)[0]
    vs, prims = kf2_tex.objetos_tmd(d[t:], por_8=False)[0]
    vs = [tuple(float(c) for c in v) for v in vs]
    desde = len(vs)
    if capucha:
        d = mo_t[MO_CAPUCHA]
        t = struct.unpack_from("<I", d, 8)[0]
        vc, pc = kf2_tex.objetos_tmd(d[t:], por_8=False)[0]
        dy = CAPUCHA_BAJO - max(v[1] for v in vc)
        vs += [(float(v[0]), float(v[1]) + dy, float(v[2])) for v in vc]
        prims = list(prims) + [(tp, cl, uvs, [r + desde for r in refs], n) for tp, cl, uvs, refs, n in pc]
    return vs, prims, desde


def rig(vs, prims, desde=None):
    """(esqueleto, dueño de cada vértice, pivotes (unidades del PS1) de cada parte, triángulos). Los vértices
    desde `desde` (la capucha) son del cuerpo."""
    esq = Esqueleto()
    duenos, ss = [], []
    for k, v in enumerate(vs):
        p, s = (1, 0.0) if desde is not None and k >= desde else _dueno(esq, v)
        duenos.append(p)
        ss.append(s)
    tris = []
    for tp, cl, uvs, refs, _ in prims:
        orden = [(0, 1, 2), (1, 3, 2)] if len(refs) == 4 else [(0, 1, 2)]
        for o in orden:
            tris.append(((tp, cl), [refs[j] for j in o], [uvs[j] for j in o]))

    def prof(p):
        n = 0
        while p > 1:
            p = esq.padre[p]
            n += 1
        return n

    # cada triángulo va con una parte y sus vértices tienen que ser de esa parte o de su padre
    for _ in range(50):
        cambio = False
        for _, refs, _ in tris:
            ps = {duenos[r] for r in refs}
            if len(ps) == 1:
                continue
            D = max(ps, key=prof)
            for r in refs:
                q = duenos[r]
                if q != D and q != esq.padre[D]:
                    # el más profundo de los dos sube un nivel
                    a = max((q, D), key=prof)
                    for r2 in refs:
                        if duenos[r2] == a:
                            duenos[r2] = esq.padre[a]
                    cambio = True
                    break
        if not cambio:
            break
    V = np.array(vs)
    piv = [np.zeros(3) for _ in range(esq.n)]
    for p in range(2, esq.n):
        pp = esq.padre[p]
        propios = [i for i in range(len(vs)) if duenos[i] == p]
        if not propios:
            piv[p] = piv[pp].copy()
            continue
        # el pivote: donde se tocan con el padre (lo más cercano al cuerpo de lo suyo)
        dist = [math.hypot(V[i, 0], V[i, 2]) + (-V[i, 1] if esq.miembro[p][0] == "brazo" else 0) for i in propios]
        orden = [propios[j] for j in np.argsort(dist)]
        piv[p] = V[orden[:max(2, len(orden) // 4)]].mean(0)
    return esq, duenos, piv, tris


# ---------------- textura: las tres páginas del PS1 en una de 256x256 y 8 bits ----------------
TEX_CONTRASTE = 1.30
TEX_COLOR = 1.45
TEX_ESCALA = 2        # las texturas del PS1 (4 bits, 64x64) se agrandan al doble suavizadas: más como las del IV


def textura(vram, tris):
    """(índices 256x256, paleta 256x4, {(tpage, clut): (dx, dy)}): cada página que usa, recortada, agrandada a
    TEX_ESCALA suavizada y todas juntas reducidas a 256 colores (las del IV son de 8 bits y más finas)."""
    from PIL import Image
    cajas = {}
    for clave, _, uvs in tris:
        u = [a for a, _ in uvs]
        v = [b for _, b in uvs]
        c = cajas.get(clave, [255, 255, 0, 0])
        cajas[clave] = [min(c[0], min(u)), min(c[1], min(v)), max(c[2], max(u)), max(c[3], max(v))]
    rgb = np.zeros((256, 256, 3), np.uint8)
    sitio = {}
    x, y, alto_fila = 0, 0, 0
    E = TEX_ESCALA
    for clave, (u0, v0, u1, v1) in sorted(cajas.items(), key=lambda kv: -(kv[1][3] - kv[1][1])):
        w, h = (u1 - u0 + 1) * E, (v1 - v0 + 1) * E
        if x + w > 256:
            x, y, alto_fila = 0, y + alto_fila, 0
        assert y + h <= 256, "no cabe la textura del pulpo"
        tp, cl = clave
        idx, p16 = _region(vram, tp, cl)
        trozo = p16[idx[v0:v1 + 1, u0:u1 + 1]][..., :3]
        grande = Image.fromarray(trozo).resize((w, h), Image.BICUBIC)
        rgb[y:y + h, x:x + w] = np.asarray(grande)
        sitio[clave] = (x - u0 * E, y - v0 * E)
        x += w
        alto_fila = max(alto_fila, h)
    # las texturas del PS1 salen apagadas al lado de las del IV: más contraste y color
    from PIL import ImageEnhance
    im = Image.fromarray(rgb)
    im = ImageEnhance.Contrast(im).enhance(TEX_CONTRASTE)
    im = ImageEnhance.Color(im).enhance(TEX_COLOR)
    rgb = np.asarray(im)
    q = Image.fromarray(rgb).quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE)
    img = np.asarray(q, np.uint8).copy()
    p = np.array(q.getpalette()[:768], np.uint8).reshape(-1, 3)
    pal = np.zeros((256, 4), np.uint8)
    pal[:len(p), :3] = p
    pal[:, 3] = 0x80
    return img, pal, sitio


def _region(vram, tpage, clut):
    px0, py0 = (tpage & 0xF) * 64, ((tpage >> 4) & 1) * 256
    cx, cy = (clut & 0x3F) * 16, (clut >> 6) & 0x1FF
    pal16 = vram[cy, cx:cx + 16].astype(np.uint32)
    pal = np.zeros((16, 4), np.uint8)
    for k, c in enumerate([(pal16 & 31), (pal16 >> 5) & 31, (pal16 >> 10) & 31]):
        pal[:, k] = (c << 3) | (c >> 2)
    pal[:, 3] = 0x80
    vacio = pal16 == 0
    if vacio.any() and not vacio.all():
        pal[vacio, :3] = pal[~vacio, :3].mean(0).astype(np.uint8)
    hw = vram[py0:py0 + 256, px0:px0 + 64].astype(np.uint32)
    idx = np.stack([(hw >> (4 * k)) & 0xF for k in range(4)], axis=2).reshape(256, 256)
    return idx.astype(np.uint8), pal


# ---------------- movimientos ----------------
def _poses(esq, nombre, f, total):
    """{parte: (giro x, giro y, giro z)} en el fotograma f de ese movimiento (radianes)."""
    t = f / max(1, total)
    w = 2 * math.pi * t
    g = {}
    cuerpo = [0.0, 0.0, 0.0]
    dy = 0.0
    for tipo, i, cad in esq.cadenas:
        az = math.radians((PATAS if tipo == "pata" else BRAZOS)[i])
        fase = i * 1.1 + (0.0 if tipo == "pata" else 2.0)
        for k, p in enumerate(cad):
            # "doblar" es subir / bajar la punta: giro alrededor del eje horizontal perpendicular a la pata
            if nombre == "quieto":
                # (con 0,10 apenas se notaba: parecía quieto del todo)
                doblar = 0.20 * math.sin(w * 2 + fase - k * 0.7) if tipo == "pata" else \
                    0.30 * math.sin(w * 2 + fase - k * 0.6)
                lado = 0.12 * math.sin(w + fase * 1.7)
            elif nombre in ("golpeado", "golpe_fuerte"):
                e = math.sin(math.pi * t) * math.exp(-2 * t) * (1.7 if nombre == "golpe_fuerte" else 1)
                doblar = -0.35 * e * (1 if tipo == "pata" else 0.4)
                lado = 0.0
            elif nombre == "muerte":
                e = min(1.0, t * 1.6)
                doblar = -(0.12 + 0.08 * k) * e if tipo == "pata" else (0.45 + 0.1 * k) * e
                lado = 0.08 * math.sin(w * 3 + fase) * (1 - e)
            elif nombre == "tinta":      # se encoge y escupe en el fotograma 40
                e = _campana(t, 0.45, 0.67, 0.85)
                doblar = (-0.25 if tipo == "pata" else -0.35) * e + (0.25 if tipo == "brazo" else 0.1) * \
                    _campana(t, 0.67, 0.72, 0.95)
                lado = 0.0
            elif nombre == "arrastrar":  # las patas en ola, de dos en dos; los brazos, un poco
                doblar = (0.28 if tipo == "pata" else 0.14) * math.sin(w * 2 + fase * 2.0 - k * 0.6)
                lado = (0.10 if tipo == "pata" else 0.05) * math.sin(w * 2 + fase)
            else:                       # latigo: los brazos atrás y luego hacia delante, golpe hacia el 28
                if tipo == "brazo":
                    atras = _campana(t, 0.0, 0.40, 0.55)
                    golpe = _campana(t, 0.40, 0.58, 1.0)
                    doblar = -0.45 * atras + (0.8 + 0.25 * k) * golpe
                    lado = (0.35 if i == 0 else -0.35) * golpe
                else:
                    doblar = 0.12 * math.sin(w * 2 + fase - k)
                    lado = 0.0
            # el eje de "doblar": perpendicular a la dirección horizontal de la pata
            ex, ez = -math.sin(az), math.cos(az)
            # pequeño giro como vector: doblar * (ex, 0, ez) + lado * (0, 1, 0) -> ángulos x, y, z (aproximación)
            g[p] = (doblar * ex, lado, doblar * ez)
    if nombre == "quieto":
        dy = 14 * math.sin(w * 2)
        cuerpo = [0.07 * math.sin(w), 0.10 * math.sin(w + 1), 0.05 * math.sin(w * 2 + 0.5)]
    elif nombre in ("golpeado", "golpe_fuerte"):
        e = math.sin(math.pi * t) * math.exp(-2 * t) * (1.7 if nombre == "golpe_fuerte" else 1)
        cuerpo = [0.18 * e, 0.0, 0.0]
        dy = -10 * e
    elif nombre == "muerte":
        e = min(1.0, t * 1.4)
        cuerpo = [0.15 * e, 0.0, 0.25 * math.sin(e * 2)]
        dy = 45 * e * e
    elif nombre == "arrastrar":
        dy = 18 * math.sin(w * 2)
        cuerpo = [0.05 * math.sin(w * 2), 0.06 * math.sin(w), 0.0]
    elif nombre == "tinta":
        cuerpo = [-0.25 * _campana(t, 0.45, 0.67, 0.85) + 0.15 * _campana(t, 0.67, 0.72, 0.95), 0, 0]
        dy = 12 * _campana(t, 0.4, 0.67, 0.9)
    else:
        cuerpo = [0.12 * _campana(t, 0.4, 0.58, 1.0) - 0.08 * _campana(t, 0.0, 0.4, 0.55), 0, 0]
    g[1] = tuple(cuerpo)
    return g, dy, (-AVANCE * t if nombre == "arrastrar" else 0.0)


def _campana(t, a, b, c):
    if t <= a or t >= c:
        return 0.0
    if t < b:
        x = (t - a) / (b - a)
    else:
        x = 1 - (t - b) / (c - b)
    return x * x * (3 - 2 * x)


def movimiento(esq, piv, nombre, total, paso=5):
    """MotionData de un movimiento: claves cada `paso` fotogramas."""
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
    curvas = []                      # por parte: [(pos, rot)] por fotograma
    for f in fots:
        g, dy, raiz = _poses(esq, nombre, f, total)
        fila = []
        for p in range(esq.n):
            if p == 0:
                pos = (0, 0, 0)
            elif p == 1:
                pos = (0, dy, 0)
            else:
                pos = tuple((piv[p] - piv[esq.padre[p]]) * ESC)
            rot = g.get(p, (0, 0, 0))
            if GIRO_180:            # el modelo va girado media vuelta (ver pulpo_chr): x y z cambian de signo
                pos = (-pos[0], pos[1], -pos[2])
                rot = (-rot[0], rot[1], -rot[2])
            if p == 0:
                pos = (0.0, 0.0, raiz)  # la raíz avanza hacia delante (-z del IV): así anda el bicho
            fila.append((pos, rot))
        curvas.append(fila)
    partes = []
    for p in range(esq.n):
        claves = []
        for j, f in enumerate(fots):
            pos, rot = curvas[j][p]
            # tangentes de Catmull-Rom, en unidades del tramo (las claves van a paso constante)
            a = curvas[max(0, j - 1)][p]
            b = curvas[min(len(fots) - 1, j + 1)][p]
            esc_t = 0.5 if 0 < j < len(fots) - 1 else 0.0
            tp = tuple((np.array(b[0]) - np.array(a[0])) * esc_t)
            tr = tuple((np.array(b[1]) - np.array(a[1])) * esc_t)
            largo = (fots[j + 1] - f) if j + 1 < len(fots) else 0
            claves.append((f, largo, v(pos), v(tp), v(tp), v(rot), v(tr), v(tr), uno))
        partes.append(claves)
    hijos = {p: esq.hijos(p) for p in range(esq.n)}
    hermano = {}
    for p, hs in hijos.items():
        for a, b in zip(hs, hs[1:]):
            hermano[a] = b
    cab = 16 + 16 * esq.n
    out = bytearray(cab)
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
    struct.pack_into("<IIIHBB", out, 0, len(out), voff, 0, total, esq.n, 0)
    for p in range(esq.n):
        hijo = hijos[p][0] if hijos[p] else 0
        struct.pack_into("<BBBBBBBBII", out, 16 + 16 * p, len(partes[p]), 0, p, hijo, hermano.get(p, 0),
                         0, 0, 0, offs[p], 0)
    return bytes(out)


# motion 0..5; la animación del IV que va a cada uno (chr.prm 0x60): 0 y 13 quieto / en guardia, 14 golpe flojo,
# 15 golpe fuerte, 16 muerte, 23 el ataque a distancia (la tinta), 20 el primer cuerpo a cuerpo (el latigazo)
ORDEN_MOV = ["quieto", "golpeado", "golpe_fuerte", "muerte", "tinta", "latigo", "arrastrar"]
# las animaciones de la babosa (registro 2): 0 quieto, 3 andar, 13 en guardia, 14 y 15 golpeado, 16 muerte, 20 el
# ataque de cerca (el latigazo)
ANIMACION = {0: 0, 3: 6, 13: 0, 14: 1, 15: 2, 16: 3, 20: 5}


def archivo_movimientos(esq, piv):
    movs = [movimiento(esq, piv, n, FOT[n]) for n in ORDEN_MOV]
    n = len(movs)
    out = bytearray(16 + 16 * n)
    off = len(out)
    pos = []
    for m in movs:
        pos.append(off)
        off += len(m)
    struct.pack_into("<IIII", out, 0, off, n, 0, 0)
    for k in range(1, n):
        struct.pack_into("<II", out, 16 + 16 * k, k - 1, pos[k - 1])
    for m in movs:
        out += m
    return bytes(out)


# ---------------- el .chr ----------------
def pulpo_chr(flor, mo_t, vram):
    """flor: kc.Chr de c0049 (la Flor oscura); mo_t: entradas de MO.T del King's Field; vram: la del nivel 0."""
    vs, prims, desde = malla_kf1(mo_t)
    esq, duenos, piv, tris = rig(vs, prims, desde)
    img, pal, sitio = textura(vram, tris)
    V = np.array(vs)
    # normales por vértice (de las caras), en ejes del IV
    nrm = np.zeros_like(V)
    for _, refs, _ in tris:
        a, b, c = V[refs[0]], V[refs[1]], V[refs[2]]
        nrm[refs] += np.cross(b - a, c - a)
    nrm /= np.maximum(1e-9, np.linalg.norm(nrm, axis=1))[:, None]
    nrm = -nrm                      # el orden del PS1 deja la normal hacia dentro
    plantilla = flor.partes[[i for i, p in enumerate(flor.partes) if p["bloques"]][0]]["bloques"][0]
    por_parte = [[] for _ in range(esq.n)]
    for clave, refs, uvs in tris:
        ps = {duenos[r] for r in refs}
        D = max(ps, key=lambda p: (p != esq.padre[min(ps)] if len(ps) > 1 else 0, p))
        if len(ps) > 1:
            D = next(p for p in ps if all(q == p or q == esq.padre[p] for q in ps))
        dx, dy = sitio[clave]
        tri = []
        for r, (u, v) in zip(refs, uvs):
            sobre_padre = duenos[r] != D
            base = piv[esq.padre[D]] if sobre_padre else piv[D]
            p = (V[r] - base) * ESC
            nr = nrm[r]
            if GIRO_180:
                p = (-p[0], p[1], -p[2])
                nr = (-nr[0], nr[1], -nr[2])
            tri.append((tuple(p), tuple(nr), _sombra(V[r], nrm[r]), ((u * TEX_ESCALA + dx + TEX_ESCALA / 2) / 256.0, (v * TEX_ESCALA + dy + TEX_ESCALA / 2) / 256.0), 1 if sobre_padre else 0))
        por_parte[D].append(tri)
    bloques = []
    for p in range(esq.n):
        bl = []
        tri_s = por_parte[p]
        for i in range(0, len(tri_s), MAX_TRIS):
            verts = []
            for tri in tri_s[i:i + MAX_TRIS]:
                # el orden del IV es el contrario del PS1: así la normal de la cara sale hacia fuera
                for k, (pos, n, col, st, sp) in enumerate([tri[0], tri[2], tri[1]] if INVERTIR else tri):
                    verts.append((pos, n, k < 2, st, sp, col))
            bl.append(kc.bloque_nuevo(plantilla, verts))
        bloques.append(bl)
    modelo = modelo_pulpo(flor, esq, bloques, piv)
    mov = archivo_movimientos(esq, piv)
    tex = kc.texturas_nuevas(flor, img, pal)
    return chr_con(flor, modelo, mov, tex), esq


MAX_TRIS = kc.MAX_V // 3


def _sombra(v, n):
    """Color de vértice (128 = sin cambiar): la cara de abajo y lo que está pegado al suelo, más oscuro; un poco de
    tono frío de agua. El IV ilumina además por la normal; esto le da el volumen que la textura del PS1 no trae."""
    arriba = (-n[1] + 1) / 2                      # 1 mirando arriba, 0 abajo (y negativa es arriba)
    alto = min(1.0, max(0.0, -v[1] / 1800.0))     # 0 en el suelo, 1 a la altura del cuerpo
    # más contraste que antes: de 0,40 por debajo a 1,25 por arriba (128 = 1; el IV deja pasar hasta 2)
    f = 0.40 + 0.55 * arriba ** 1.5 + 0.30 * alto
    return (min(255.0, 128 * f * 0.94), min(255.0, 128 * f), min(255.0, 128 * f * 1.02), 128.0)
INVERTIR = True
MAGIA_CHORRO = 58           # param/magic.prm: Hidrocañón (Hydro Cannon) nivel 1, la magia de agua del jugador
# el Kraken del King's Field mira hacia +z (los dos brazos largos y los ojos están de ese lado) y los bichos del IV
# miran hacia -z: sin girarlo salía mirando al lado contrario. Media vuelta alrededor del eje vertical (un giro, no
# un espejo: las caras y las normales siguen igual) de los vértices, los huesos y los giros de los movimientos
GIRO_180 = True


def modelo_pulpo(flor, esq, bloques, piv):
    d, m = flor.d, flor.m
    n = esq.n
    cab = bytearray(0x210 + 16 * n)
    struct.pack_into("<IH", cab, 0, 0, n)
    # anclas: 0 y 1 en la boca (donde sale la tinta), el resto vacías
    boca = np.array([0.0, -1500.0, -720.0]) * ESC
    for k in range(32):
        if k < 2:
            struct.pack_into("<3fB", cab, 0x10 + 16 * k, boca[0], boca[1], boca[2] - 10 * k, 1)
        else:
            struct.pack_into("<3fB", cab, 0x10 + 16 * k, 0, 0, 0, 0xFF)
    cuerpo = bytearray()
    base = len(cab) + (-len(cab)) % 16
    for p in range(n):
        off = base + len(cuerpo)
        struct.pack_into("<IHBb", cab, 0x210 + 16 * p, off, len(bloques[p]), 1 if p == 0 else 0,
                         esq.padre[p] if esq.padre[p] >= 0 else -1)
        for b in bloques[p]:
            cuerpo += b
    out = bytearray(bytes(cab).ljust(base, b"\0") + cuerpo)
    out += bytes((-len(out)) % 16)
    struct.pack_into("<I", out, 0, len(out))
    return bytes(out)


def chr_con(flor, modelo, mov, tex):
    d = flor.d
    c = flor.cab
    secciones = sorted({c[1], c[2], c[3], c[4], c[5], c[6], len(d)})
    trozos = {a: d[a:b] for a, b in zip(secciones, secciones[1:])}
    trozos[c[1]] = modelo
    trozos[c[2]] = mov
    trozos[c[3]] = tex
    out = bytearray(d[:secciones[0]])
    nuevo = {}
    for a in secciones[:-1]:
        out += bytes((-len(out)) % 16)
        nuevo[a] = len(out)
        out += trozos[a]
    out += bytes((-len(out)) % 16)
    cab = list(c)
    for k in range(1, 7):
        if cab[k] in nuevo:
            cab[k] = nuevo[cab[k]]
    struct.pack_into("<8I", out, 0, *cab)
    return bytes(out)


# ---------------- chr.prm ----------------
def pulpo_prm(base_rec):
    """El registro del pulpo a partir del de la babosa (registro 2): su IA se acerca arrastrándose y ataca de cerca,
    y el arrastrarse mueve al bicho con la raíz del movimiento (como el caracol)."""
    r = bytearray(base_rec)
    struct.pack_into("<H", r, 0, MODELO_PULPO)
    struct.pack_into("<H", r, 0x0A, 400)          # vida
    struct.pack_into("<H", r, 0x0E, 450)          # experiencia (la del King's Field: 450)
    struct.pack_into("<H", r, 0x06, 120)          # radio contra el mapa
    struct.pack_into("<H", r, 0x08, 250)          # alto contra el mapa
    struct.pack_into("<H", r, 0xEE, 250)          # alto del cuerpo
    r[0xD2] = 100                                 # escala
    r[0x11] &= ~0x40                              # la babosa es semitransparente; el pulpo no
    ids = [0] * 0x20
    for anim in range(17, 0x20):     # no sé qué índice usa la IA de la babosa para atacar (en la babosa todos van
        ids[anim] = 5                # al 0): todos los de ataque, al latigazo
    for anim, mov in ANIMACION.items():
        ids[anim] = mov
    r[0x60:0x80] = bytes(ids)
    # el latigazo: el ataque de cerca de la babosa, en la ventana del movimiento nuevo y con el alcance de los brazos
    o = 0x240
    # todo como en la babosa (su ataque sí sale en el juego), cambiando solo el alcance, el golpe y su ventana
    r[o + 0] = 100            # peso
    r[o + 1] = 0
    r[o + 2] = 0
    r[o + 3] = 0
    struct.pack_into("<HHf", r, o + 4, 0, 300, math.pi)
    h = o + 0x10
    struct.pack_into("<9h", r, h, 0, 35, 0, 0, 0, 0, 15, 0, 0)  # golpe y agua
    struct.pack_into("<HHHH", r, h + 0x20, 450, 180, 26, 34)
    # sin ataque a distancia: las magias de los bichos salían sin textura en este mapa, y la del jugador
    # (Hidrocañón) también (sus texturas solo se cargan si la llevas puesta)
    r[0x3D8] = 0
    return bytes(r)


def mini_prm(grande_rec):
    """El pulpito: el registro del grande a la escala de su clase, con la vida y la experiencia del King's Field
    (patas 250 + capucha 250 de vida en el original, a la cuarta parte como todo lo portado; 12 + 3 de experiencia)."""
    r = bytearray(grande_rec)
    struct.pack_into("<H", r, 0x0A, 125)
    struct.pack_into("<H", r, 0x0E, 15)
    r[0xD2] = MINI_ESCALA
    h = 0x240 + 0x10
    struct.pack_into("<9h", r, h, 0, 18, 0, 0, 0, 0, 8, 0, 0)          # golpe y agua: más flojo que el grande
    struct.pack_into("<HHf", r, 0x240 + 4, 0, 120, math.pi)              # alcance a su tamaño
    struct.pack_into("<HHHH", r, h + 0x20, 160, 70, 26, 34)
    return bytes(r)
