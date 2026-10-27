#!/usr/bin/env python3
"""
kf4_esqueleto.py - El esqueleto del King's Field (MO.T[21]) como enemigo nuevo del King's Field IV.

Su modelo y su textura del PS1 (con más contraste y color y luz de vértice propia), montados sobre los huesos del
Skeleton Soldier del IV (c0050): cada trozo del cuerpo del King's Field (cabeza, costillas, brazos, piernas, la
espada) se lleva a la postura de reposo del soldado y se guarda en el espacio de su hueso. Así usa los movimientos
del propio soldado (andar, guardia, los dos espadazos, golpes, muerte...) y su IA, que esperan justo esos huesos.

  esqueleto_chr(soldado, mo_t, vram) -> bytes del .chr nuevo (chr/c0150.chr, vacío en el IV)
  esqueleto_prm(registro_soldado)    -> registro de chr.prm (el 77, vacío en el IV)
"""

import struct

import numpy as np

import kf2_tex
import kf4_chr as kc
import kf4_pulpo as kp

MODELO = 150                 # chr/c0150.chr: archivo vacío de 32 bytes en el IV
REGISTRO = 77                # chr.prm 77: vacío en el IV
REGISTRO_BASE = 50           # el Skeleton Soldier (c0050): sus huesos, sus movimientos y su IA
MO_ESQUELETO = 21
ALTO_IV = 190.0              # cm: el soldado del IV mide unos 2 m con el casco; el esqueleto, algo menos
VIDA, EXP = 175, 40          # el King's Field: 800 / 600 / 400 de vida (a la cuarta parte) y 37-52 de experiencia

# huesos del soldado (c0050): 2 cadera, 3-6 pierna (x < 0: muslo, espinilla, pie, dedos), 7-10 la otra,
# 11 vientre, 12 pecho, 13-16 brazo x > 0 (brazo, antebrazo, mano, escudo), 17 cuello, 18 cabeza, 19 mandíbula,
# 20-23 brazo x < 0 (brazo, antebrazo, mano, espada)
# articulaciones del esqueleto del King's Field (unidades del PS1, h = altura = -y): inicio y fin de cada trozo
_J = {
    "cadera": ((0, 960, 0), (0, 1060, 0)),
    "vientre": ((0, 1060, 0), (0, 1200, 0)),
    "pecho": ((0, 1200, 0), (0, 1540, 0)),
    "cuello": ((0, 1540, 0), (0, 1610, 0)),
    "cabeza": ((0, 1610, 0), (0, 1800, 0)),
}
for _s, _l in ((-1, "i"), (1, "d")):
    _J["muslo" + _l] = ((75 * _s, 960, 0), (80 * _s, 560, 0))
    _J["espinilla" + _l] = ((80 * _s, 560, 0), (80 * _s, 100, 0))
    _J["pie" + _l] = ((80 * _s, 100, 0), (80 * _s, 0, -120))
    _J["brazo" + _l] = ((235 * _s, 1520, 0), (240 * _s, 1180, 0))
    _J["antebrazo" + _l] = ((240 * _s, 1180, 0), (240 * _s, 790, 0))
    _J["mano" + _l] = ((240 * _s, 790, 0), (240 * _s, 620, 0))
_J["espada"] = ((-200, 690, 0), (-200, 690, -870))
HUESO = {"cadera": 2, "vientre": 11, "pecho": 12, "cuello": 17, "cabeza": 18,
         "muslod": 7, "espinillad": 8, "pied": 9, "musloi": 3, "espinillai": 4, "piei": 5,
         "brazod": 13, "antebrazod": 14, "manod": 15, "brazoi": 20, "antebrazoi": 21, "manoi": 22, "espada": 23}
# el hueso del soldado cuyo origen es el final de cada trozo (para su dirección y su largo)
HIJO = {2: 11, 11: 12, 12: 17, 17: 18, 3: 4, 4: 5, 7: 8, 8: 9, 13: 14, 14: 15, 20: 21, 21: 22}


def _trozo(v):
    """Trozo del cuerpo del King's Field de un vértice (x, y, z del PS1)."""
    x, h, z = v[0], -v[1], v[2]
    lado = "i" if x < 0 else "d"
    if x < -150 and (z < -150 or z > 120) and 560 < h < 820:
        return "espada"
    if h >= 1610:
        return "cabeza"
    if abs(x) >= 160 and 560 < h < 1580:
        if h >= 1180:
            return "brazo" + lado
        if h >= 790:
            return "antebrazo" + lado
        return "mano" + lado
    if h >= 1540:
        return "cuello"
    if h >= 1200:
        return "pecho"
    if h >= 1060:
        return "vientre"
    if h >= 900:
        return "cadera"
    if h >= 560:
        return "muslo" + lado
    if h >= 100:
        return "espinilla" + lado
    return "pie" + lado


def _girar(a, b):
    """Matriz 3x3 que lleva la dirección a a la b (por el camino más corto)."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else -np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * (1 / (1 + c))


def malla(mo_t):
    d = mo_t[MO_ESQUELETO]
    t = struct.unpack_from("<I", d, 8)[0]
    vs, prims = kf2_tex.objetos_tmd(d[t:], por_8=False)[0]
    return [tuple(float(c) for c in v) for v in vs], prims


def esqueleto_chr(base, mo_t, vram):
    """base: kc.Chr del Skeleton Soldier (c0050)."""
    vs, prims = malla(mo_t)
    V = np.array(vs)
    W = base.pose(0, 0)                         # la postura de reposo del soldado (su movimiento 0)
    padre = base.jerarquia(0)
    n = base.n_partes
    esc = ALTO_IV / (-V[:, 1].min())
    org = [w[:3, 3] for w in W]
    # cada trozo: su giro hasta la postura del soldado, su escala y su punto de inicio
    trans = {}
    for nombre, hueso in HUESO.items():
        (a, b) = _J[nombre]
        a_k = np.array([a[0], -a[1], a[2]], float) * esc
        b_k = np.array([b[0], -b[1], b[2]], float) * esc
        if hueso in HIJO:
            a_c, b_c = org[hueso], org[HIJO[hueso]]
        elif nombre == "espada":
            a_c = org[hueso]
            b_c = a_c + W[hueso][:3, :3] @ np.array([0.0, 0.0, -100.0])      # la hoja del soldado va a -z
        else:                                   # puntas (pies, manos, cabeza): la dirección de su propio hueso
            a_c = org[hueso]
            eje = np.array([0.0, 1.0, 0.0]) if nombre != "cabeza" else np.array([0.0, -1.0, 0.0])
            b_c = a_c + W[hueso][:3, :3] @ eje * np.linalg.norm(b_k - a_k)
        R = _girar(b_k - a_k, b_c - a_c)
        k = np.linalg.norm(b_c - a_c) / max(1e-6, np.linalg.norm(b_k - a_k))
        k = min(1.6, max(0.6, k))
        trans[nombre] = (R, k, a_k, a_c)
    trozos = [_trozo(v) for v in vs]
    duenos = [HUESO[t] for t in trozos]
    # triángulos (de 3 y de 4 lados, como el PS1) y vértices de cada parte o de su padre (la costura)
    tris = []
    for tp, cl, uvs, refs, _ in prims:
        orden = [(0, 1, 2), (1, 3, 2)] if len(refs) == 4 else [(0, 1, 2)]
        for o in orden:
            tris.append(((tp, cl), [refs[j] for j in o], [uvs[j] for j in o]))

    def prof(p):
        c = 0
        while padre[p] >= 0:
            p = padre[p]
            c += 1
        return c
    for _ in range(60):
        cambio = False
        for _, refs, _ in tris:
            ps = {duenos[r] for r in refs}
            if len(ps) == 1:
                continue
            D = max(ps, key=prof)
            if all(q == D or q == padre[D] for q in ps):
                continue
            # un triángulo entre partes no seguidas: sus vértices de la parte más honda pasan a la otra
            a = max(ps, key=prof)
            otro = min(ps, key=prof)
            for r in refs:
                if duenos[r] == a:
                    duenos[r] = otro
            cambio = True
        if not cambio:
            break
    # posiciones en la postura del soldado (cm) y normales
    P = np.zeros_like(V)
    for i, v in enumerate(vs):
        nombre = trozos[i]
        R, k, a_k, a_c = trans[nombre]
        P[i] = a_c + k * (R @ (np.array([v[0], v[1], v[2]]) * esc - a_k))
    img, pal, sitio = kp.textura(vram, tris)
    # el hueso del PS1 sale gris: un poco de tono de hueso viejo
    pal = pal.copy()
    pal[:, :3] = np.clip(pal[:, :3].astype(float) * np.array([1.12, 1.04, 0.86]), 0, 255).astype(np.uint8)
    nrm = np.zeros_like(P)
    for _, refs, _ in tris:
        a, b, c = P[refs[0]], P[refs[1]], P[refs[2]]
        nrm[refs] += np.cross(b - a, c - a)
    nrm /= np.maximum(1e-9, np.linalg.norm(nrm, axis=1))[:, None]
    nrm = -nrm
    inv = [np.linalg.inv(w) for w in W]
    plantilla = base.partes[[i for i, p in enumerate(base.partes) if p["bloques"]][0]]["bloques"][0]
    por_parte = [[] for _ in range(n)]
    E = kp.TEX_ESCALA
    for clave, refs, uvs in tris:
        ps = {duenos[r] for r in refs}
        D = next(p for p in ps if all(q == p or q == padre[p] for q in ps))
        dx, dy = sitio[clave]
        tri = []
        for r, (u, v) in zip(refs, uvs):
            sobre_padre = duenos[r] != D
            M = inv[padre[D]] if sobre_padre else inv[D]
            p = (M @ np.append(P[r], 1.0))[:3]
            nr = M[:3, :3] @ nrm[r]
            nr /= max(1e-9, np.linalg.norm(nr))
            # la luz de vértice: como el pulpo, con la altura del King's Field (0 en el suelo)
            tri.append((tuple(p), tuple(nr), kp._sombra(V[r], nrm[r]),
                        ((u * E + dx + E / 2) / 256.0, (v * E + dy + E / 2) / 256.0), 1 if sobre_padre else 0))
        por_parte[D].append(tri)
    bloques = []
    for p in range(n):
        bl, ts = [], por_parte[p]
        for i in range(0, len(ts), kp.MAX_TRIS):
            verts = []
            for tri in ts[i:i + kp.MAX_TRIS]:
                for k, (pos, nn, col, st, sp) in enumerate([tri[0], tri[2], tri[1]]):
                    verts.append((pos, nn, k < 2, st, sp, col))
            bl.append(kc.bloque_nuevo(plantilla, verts))
        bloques.append(bl)
    # el ModelFile: la cabecera del soldado (sus anclas: las manos) con los bloques nuevos
    d, m = base.d, base.m
    cab = bytearray(d[m:m + 0x210 + 16 * n])
    cuerpo = bytearray()
    base_off = len(cab) + (-len(cab)) % 16
    for p in range(n):
        # el padre de cada parte en la cabecera del modelo (el bicho del IV lo trae a -1): los vértices "del padre"
        # (las costuras) se ponen con la matriz de esa parte; con -1 salían estirados por el suelo
        struct.pack_into("<IH", cab, 0x210 + 16 * p, base_off + len(cuerpo), len(bloques[p]))
        struct.pack_into("<b", cab, 0x210 + 16 * p + 7, padre[p] if padre[p] >= 0 else -1)
        for b in bloques[p]:
            cuerpo += b
    modelo = bytearray(bytes(cab).ljust(base_off, b"\0") + cuerpo)
    modelo += bytes((-len(modelo)) % 16)
    struct.pack_into("<I", modelo, 0, len(modelo))
    mov = d[base.mot:sorted(x for x in set(base.cab[1:7]) | {len(d)} if x > base.mot)[0]]
    datos = bytearray(kp.chr_con(base, bytes(modelo), mov, kc.texturas_nuevas(base, img, pal)))
    # el modelo de "pool" del soldado (otra copia de su cuerpo, más sencilla) se usa si tiene las mismas partes
    # que el modelo: se le cambia el número de partes para que el juego no lo use (si no, se vería el soldado)
    cabs = struct.unpack_from("<8I", datos, 0)
    if cabs[4] and cabs[4] < len(datos):
        struct.pack_into("<H", datos, cabs[4] + 4, 1)
    return bytes(datos)


def esqueleto_prm(base_rec):
    """El registro del soldado (su IA, sus dos espadazos, sus sonidos y animaciones) con el modelo, la vida y la
    experiencia del esqueleto del King's Field."""
    r = bytearray(base_rec)
    struct.pack_into("<H", r, 0, MODELO)
    struct.pack_into("<H", r, 0x0A, VIDA)
    struct.pack_into("<H", r, 0x0E, EXP)
    return bytes(r)
