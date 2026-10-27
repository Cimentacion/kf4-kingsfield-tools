#!/usr/bin/env python3
"""
kf4_portar.py - Bichos del King's Field (MO.T) montados sobre los huesos de un bicho parecido del King's Field IV.

El modelo y la textura del PS1 (con más contraste y color y luz de vértice propia) se colocan sobre la postura de
reposo del bicho del IV (su movimiento 0): mismo suelo, mismo centro, del tamaño del del IV y girado como él
(se prueban las cuatro vueltas y se queda la que mejor encaja). Cada vértice va al hueso del bicho del IV que tiene
más cerca. Así el bicho nuevo usa los movimientos y la IA del del IV, que esperan justo esos huesos.

  portar_chr(base, mo_t, vram, cfg)  -> bytes del .chr nuevo
  portar_prm(registro_base, cfg)     -> registro de chr.prm

cfg (BICHOS): modelo (chr/cNNNN.chr que no usa ningún registro del IV), registro (vacío en el IV), base (registro
del bicho del IV del que salen los huesos, los movimientos, la IA y los sonidos), mo (entrada de MO.T), vida,
experiencia, tinte de la textura, escala (sobre el tamaño del del IV).
"""

import struct

import numpy as np

import kf2_tex
import kf4_chr as kc
import kf4_pulpo as kp

# kf1 = modelo del King's Field (MO.T); los nombres de la tabla de enemigos de kf1_objetos
BICHOS = {
    "babosa": dict(kf1=0, modelo=94, registro=94, base=2, vida=75, exp=3, tinte=(0.95, 1.10, 0.90), escala=1.0,
                   texto="Babosa verde del King's Field (se porta como la babosa del IV)"),
    "head_eater": dict(kf1=14, modelo=95, registro=95, base=4, vida=70, exp=7, tinte=(1.0, 1.0, 1.0), escala=1.0,
                       texto="Head Eater del King's Field (la planta del IV: c0004)"),
    "baltail": dict(kf1=4, modelo=96, registro=96, base=10, vida=60, exp=22, tinte=(1.0, 1.0, 1.0), escala=1.0,
                    centro=True, texto="Baltail del King's Field (vuela y ataca como el murciélago del IV)"),
    # los del agua: con el Seafang del IV (nada bajo el agua); el registro es el del pez (kf4_valle.registro_pez)
    "sigill": dict(kf1=2, modelo=152, registro=None, base=43, vida=0, exp=0, tinte=(1.0, 1.0, 1.0), escala=1.0,
                   centro=True, texto="Sigill del King's Field (nada como el Seafang del IV)"),
    "anguila": dict(kf1=5, modelo=164, registro=100, base=43, vida=0, exp=0, tinte=(1.0, 1.0, 1.0), escala=1.0,
                    centro=True, texto="Pez largo del King's Field (el 5; nada como el Seafang del IV)"),
}


def _malla(mo_t, n):
    d = mo_t[n]
    t = struct.unpack_from("<I", d, 8)[0]
    vs, prims = kf2_tex.objetos_tmd(d[t:], por_8=False)[0]
    return np.array([[float(c) for c in v] for v in vs]), prims


def _posada(base):
    W = base.pose(0, 0)
    P, I = [], []
    for i in range(base.n_partes):
        for b in base.partes[i]["bloques"]:
            for v in kc.Chr.vertices(b):
                P.append((W[i] @ np.array([*v["p"], 1.0]))[:3])
                I.append(i)
    return W, np.array(P), np.array(I)


def _encajar(V, P, escala=1.0, centro=False):
    """V (PS1) colocado sobre la nube P del bicho del IV: (posiciones, giro elegido, error)."""
    lo, hi = P.min(0), P.max(0)
    tam_iv = np.linalg.norm(hi - lo)
    mejor = None
    for k in range(4):
        a = k * np.pi / 2
        R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        Q = V @ R.T
        qlo, qhi = Q.min(0), Q.max(0)
        s = tam_iv / max(1e-6, np.linalg.norm(qhi - qlo)) * escala
        Q = Q * s
        qlo, qhi = Q.min(0), Q.max(0)
        # mismo suelo (y mayor = más abajo) y mismo centro en x, z
        d = (lo + hi) / 2 - (qlo + qhi) / 2
        if not centro:                          # los que andan: mismo suelo; los que vuelan, mismo centro
            d[1] = hi[1] - qhi[1]
        Q = Q + d
        dist = np.sqrt(((Q[:, None, :] - P[None, :, :]) ** 2).sum(-1)).min(1)
        err = dist.mean()
        if mejor is None or err < mejor[2]:
            mejor = (Q, k, err)
    return mejor


def portar_chr(base, mo_t, vram, cfg):
    V, prims = _malla(mo_t, cfg["kf1"])
    W, P, I = _posada(base)
    Q, giro, _ = _encajar(V, P, cfg.get("escala", 1.0), cfg.get("centro", False))
    padre = base.jerarquia(0)
    n = base.n_partes
    d2 = ((Q[:, None, :] - P[None, :, :]) ** 2).sum(-1)
    duenos = [int(I[j]) for j in d2.argmin(1)]
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

    def antepasados(p):
        out = []
        while p >= 0:
            out.append(p)
            p = padre[p]
        return out
    for _ in range(80):              # cada triángulo: vértices de una parte o de su padre
        cambio = False
        for _, refs, _ in tris:
            ps = {duenos[r] for r in refs}
            if len(ps) == 1:
                continue
            D = max(ps, key=prof)
            if all(q == D or q == padre[D] for q in ps):
                continue
            # lo lleva todo al antepasado común más hondo
            comun = set(antepasados(next(iter(ps))))
            for q in ps:
                comun &= set(antepasados(q))
            c = max(comun, key=prof) if comun else 0
            for r in refs:
                duenos[r] = c
            cambio = True
        if not cambio:
            break
    img, pal, sitio = kp.textura(vram, tris)
    t = np.array(cfg.get("tinte", (1, 1, 1)))
    pal = pal.copy()
    pal[:, :3] = np.clip(pal[:, :3].astype(float) * t, 0, 255).astype(np.uint8)
    nrm = np.zeros_like(Q)
    for _, refs, _ in tris:
        a, b, c = Q[refs[0]], Q[refs[1]], Q[refs[2]]
        nrm[refs] += np.cross(b - a, c - a)
    nrm /= np.maximum(1e-9, np.linalg.norm(nrm, axis=1))[:, None]
    nrm = -nrm
    alto = max(1e-6, Q[:, 1].max() - Q[:, 1].min())
    inv = [np.linalg.inv(w) for w in W]
    plantilla = base.partes[[i for i, p in enumerate(base.partes) if p["bloques"]][0]]["bloques"][0]
    por_parte = [[] for _ in range(n)]
    E = kp.TEX_ESCALA
    for clave, refs, uvs in tris:
        ps = {duenos[r] for r in refs}
        D = next((p for p in ps if all(q == p or q == padre[p] for q in ps)), max(ps, key=prof))
        dx, dy = sitio[clave]
        tri = []
        for r, (u, v) in zip(refs, uvs):
            sobre_padre = duenos[r] != D
            M = inv[padre[D]] if sobre_padre and padre[D] >= 0 else inv[D]
            p = (M @ np.append(Q[r], 1.0))[:3]
            nr = M[:3, :3] @ nrm[r]
            nr /= max(1e-9, np.linalg.norm(nr))
            # luz de vértice como el pulpo, con la altura del bicho llevada a la escala del PS1 de 1800
            h = (Q[:, 1].max() - Q[r, 1]) / alto * 1800.0
            tri.append((tuple(p), tuple(nr), kp._sombra((0.0, -h, 0.0), nrm[r]),
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
    fin = sorted(x for x in set(base.cab[1:7]) | {len(d)} if x > base.mot)[0]
    mov = d[base.mot:fin]
    datos = bytearray(kp.chr_con(base, bytes(modelo), mov, kc.texturas_nuevas(base, img, pal)))
    cabs = struct.unpack_from("<8I", datos, 0)
    if cabs[4] and cabs[4] < len(datos):       # el modelo de "pool" del bicho del IV: que no se use
        struct.pack_into("<H", datos, cabs[4] + 4, 1)
    return bytes(datos)


def portar_prm(base_rec, cfg):
    r = bytearray(base_rec)
    struct.pack_into("<H", r, 0, cfg["modelo"])
    struct.pack_into("<H", r, 0x0A, cfg["vida"])
    struct.pack_into("<H", r, 0x0E, cfg["exp"])
    return bytes(r)
