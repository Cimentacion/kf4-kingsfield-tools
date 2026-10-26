#!/usr/bin/env python3
"""
kf2_a_editor.py - Convierte el trazado de un nivel de King's Field II (PS1, SLUS-00255) en un mapa del
Editor de la Torre (mapa_torre.json), con las texturas de King's Field IV.

Lo que se sabe del formato viene de github.com/AnatoliySolomichev/kings_field_2_re (FORMATS.md):
  FDAT.T es un archivo .T (u16 n, u16[n+1] inicios en sectores de 2048); cada nivel son 3 entradas y la
  primera (3n) empieza por u32 64000 y una rejilla de 80 x 80 casillas de 10 bytes, índice (z * 80 + x) * 10:
    +5 textura de la pared/superficie (255 en roca maciza)
    +6 altura del suelo (y del mundo = -128 * altura; una casilla mide 2048)
    +8 forma de la casilla (255 = no hay casilla: roca)
    +9 flags (0x40: la casilla lleva una cara vertical)

Esta primera versión porta el trazado:
  - casillas transitables -> terreno con la altura de KF2 (vértice = media de las casillas que lo tocan)
  - roca junto a lo transitable -> bloques que hacen de pared (hasta el techo en interiores, riscos fuera)
  - interiores -> techo a ALTO_TECHO sobre el suelo
  - la textura de cada casilla de KF2 se reparte entre las del 4 por frecuencia (mismo dibujo, otra piel)
Objetos, enemigos y puertas aún no.

Uso: python kf2_a_editor.py FDAT.T|juego.cue|carpeta NIVEL [salida.json] [--interior | --exterior]
"""

import base64
import collections
import io
import json
import math
import os
import struct
import sys

N_KF2 = 80
CELDA = 2.5                        # metros por casilla (KF2: 2048 unidades)
ALTURA_M = 128 / 2048 * CELDA      # metros por unidad de altura de KF2
ALTO_TECHO = 3.0                   # interiores: altura libre mínima
PASO_TECHO = 2.5                   # los techos van a múltiplos de esto: menos faldones entre techos
PASO_TECHO_KF1 = 1.25              # King's Field (KF2 japonés): techos propios de cada casilla, redondeados a esto
ALTO_RISCO = 8.0                   # exteriores: la roca sube esto sobre el suelo más alto que toca
N_EDITOR = 96
SALTO_RECTO = 1.3                          # m: un desnivel mayor entre casillas vecinas es una pared recta, no rampa (KF: un escalón de casilla son 1,25 m y hay que poder subirlo)
SALTO_ZONA = 1.8          # desnivel máximo entre casillas para contarlas en la misma zona (elegir el inicio)
CLARO_PARED = 0x9C9890                     # color de vértice de lo alto de las paredes (128 = sin cambio)
PALETA = ["vacio", "losas", "sillar", "muro", "roca", "roca_gris", "musgo", "grava", "piedra_lisa", "ladrillo",
          "banda", "estrias", "madera", "friso", "nicho"]
SUELOS_INTERIOR = ["losas", "piedra_lisa", "sillar", "grava", "ladrillo", "madera"]
SUELOS_EXTERIOR = ["musgo", "grava", "losas", "roca_gris", "piedra_lisa", "sillar"]


def leer_archivos(ruta, nombres=("FDAT.T", "RTIM.T", "RTMD.T")):
    """{nombre: entradas} de los .T de King's Field II: de una carpeta con ellos sueltos (p. ej. la de
    kf2_datos.zip descomprimido, con CD/COM/) o de la imagen del disco (.cue, .bin o su carpeta)."""
    out = {}
    if os.path.isdir(ruta):
        for nombre in nombres:
            for cand in (os.path.join(ruta, nombre), os.path.join(ruta, "CD", "COM", nombre)):
                if os.path.isfile(cand):
                    out[nombre] = _t(open(cand, "rb").read())
    elif ruta.lower().endswith(".t"):
        out[os.path.basename(ruta).upper()] = _t(open(ruta, "rb").read())
        carpeta = os.path.dirname(ruta)
        for nombre in nombres:
            if nombre not in out and os.path.isfile(os.path.join(carpeta, nombre)):
                out[nombre] = _t(open(os.path.join(carpeta, nombre), "rb").read())
    if len(out) == len(nombres):
        return out
    import kf2_extraer as kx
    binario = kx.buscar_bin(ruta if not ruta.lower().endswith(".t") else os.path.dirname(ruta))
    if not binario:
        if "FDAT.T" in out:
            return out
        raise FileNotFoundError(f"No encuentro el .bin del juego ni FDAT.T en {ruta}")
    disco = kx.Disco(binario)
    lista = disco.archivos()
    for nombre in nombres:
        e = next((x for x in lista if x[0].upper().endswith("/" + nombre)), None)
        if e is not None:
            out[nombre] = _t(disco.leer(e[1], e[2]))
    if "FDAT.T" not in out:
        raise FileNotFoundError("Ese disco no tiene CD/COM/FDAT.T: ¿es King's Field II (SLUS-00255)?")
    return out


def leer_t(ruta):
    return leer_archivos(ruta)["FDAT.T"]


def _t(d):
    n = struct.unpack_from("<H", d, 0)[0]
    off = struct.unpack_from(f"<{n + 1}H", d, 2)
    return [d[off[i] * 2048:off[i + 1] * 2048] for i in range(n)]


def rejilla(entradas, nivel):
    e = entradas[3 * nivel]
    if struct.unpack_from("<I", e, 0)[0] != 64000:
        raise ValueError(f"El nivel {nivel} no tiene la rejilla de 80 x 80")
    g = e[4:4 + 64000]
    celdas = {}
    for z in range(N_KF2):
        for x in range(N_KF2):
            c = g[(z * N_KF2 + x) * 10:(z * N_KF2 + x) * 10 + 10]
            celdas[(x, z)] = {"tex": c[5], "h": c[6], "forma": c[8], "flags": c[9]}
    return celdas


def juego_de(arch):
    """'kf1': King's Field europeo/USA (KF2 japonés), 9 mapas; 'kf3': King's Field II USA (KF3 japonés)."""
    return "kf1" if len(arch["FDAT.T"]) < 100 else "kf3"


BASE_VRAM = {"kf1": 47, "kf3": 96}          # entrada de FDAT.T con las texturas comunes


def _tipos_casilla(objs):
    """Por modelo de casilla: (tiene suelo a su altura, altura del techo por encima en unidades, tiene paredes)."""
    import numpy as np
    out = []
    for verts, prims in objs:
        suelo, techos, paredes = False, [], False
        for _, _, _, refs, _n in prims:
            P = [np.array(verts[r], float) for r in refs]
            nrm = np.cross(P[1] - P[0], P[2] - P[0])
            nn = np.linalg.norm(nrm)
            if nn == 0:
                continue
            y = np.mean([q[1] for q in P])
            if abs(nrm[1]) / nn > 0.7:
                if abs(y) < 300:
                    suelo = True
                elif y < -1000:
                    techos.append(-y)
            else:
                paredes = True
        out.append((suelo, min(techos) / 128.0 if techos else None, paredes))
    return out


ESCALA_KF = CELDA / 2048           # metros por unidad de los modelos del PS1
PASO_RAMPA = 0.3                   # m: desnivel mínimo entre un lado y el opuesto para tratar la casilla como rampa


def _girar_kf(v, rot):
    x, y, z = v
    for _ in range(rot & 3):
        x, y, z = z, y, -x
    return x, y, z


def _suelo_en(tris, px, pz, bajo, alto):
    """Altura (m, hacia arriba, sobre la casilla) del suelo más alto en (px, pz) entre `bajo` y `alto` (lo que
    queda fuera, como el tejado de una torre o el fondo bajo un muelle, no cuenta); None si no hay."""
    mejor = None
    for (a, b, c) in tris:
        d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
        if abs(d) < 1e-6:
            continue
        l1 = ((b[2] - c[2]) * (px - c[0]) + (c[0] - b[0]) * (pz - c[2])) / d
        l2 = ((c[2] - a[2]) * (px - c[0]) + (a[0] - c[0]) * (pz - c[2])) / d
        l3 = 1 - l1 - l2
        if min(l1, l2, l3) < -1e-3:
            continue
        h = l1 * a[1] + l2 * b[1] + l3 * c[1]
        if bajo <= h <= alto and (mejor is None or h > mejor):
            mejor = h
    return mejor


def _tris_suelo(objs, t, rot):
    """Triángulos de suelo del modelo (x, altura en m, z), girado."""
    verts, prims = objs[t]
    tris = []
    for _, _, _, refs, _n in prims:
        P = [_girar_kf(verts[r], rot) for r in refs]
        P = [(q[0], -q[1] * ESCALA_KF, q[2]) for q in P]
        for tri in ((0, 1, 2), (1, 3, 2)) if len(P) == 4 else ((0, 1, 2),):
            a, b, c = (P[i] for i in tri)
            u = (b[0] - a[0], (b[1] - a[1]) / ESCALA_KF, b[2] - a[2])
            w = (c[0] - a[0], (c[1] - a[1]) / ESCALA_KF, c[2] - a[2])
            n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
            ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
            if ln > 0 and abs(n[1]) / ln > 0.7:
                tris.append((a, b, c))
    return tris


def suelo_de(objs, t, cache):
    """Altura (m) del suelo por el que se anda en el modelo, sobre la altura de la casilla: la más repetida en
    una rejilla de 5 x 5 puntos (el modelo 74 del nivel 0, junto al muelle, tiene todo el suelo a +0,78 m; con
    la altura de la casilla la colisión quedaba 0,78 m por debajo de lo que se ve). 0 si no tiene suelo."""
    if t in cache:
        return cache[t]
    tris = _tris_suelo(objs, t, 0)
    out = 0.0
    if tris:
        vals = [_suelo_en(tris, px, pz, -0.5, 2.0) for px in (-864, -432, 0, 432, 864) for pz in (-864, -432, 0, 432, 864)]
        vals = [round(v, 2) for v in vals if v is not None]
        if vals:
            out = collections.Counter(vals).most_common(1)[0][0]
    cache[t] = out
    return out


def _banda_escalera(tris, defecto):
    """Si los suelos del modelo forman una escalera (4 o más alturas seguidas a menos de 0,8 m unas de otras que
    suben 1,5 m o más; la escalera de caracol de la torre del nivel 0 sube 2,5 m por casilla y empieza a +17,8 m
    en la última), la banda de alturas de esa escalera; si no, `defecto`."""
    niveles = sorted({round(max(a[1], b[1], c[1]), 2) for a, b, c in tris})
    mejor, ini = None, 0
    for i in range(1, len(niveles) + 1):
        if i == len(niveles) or niveles[i] - niveles[i - 1] > 0.8:
            tramo = niveles[ini:i]
            if len(tramo) >= 4 and tramo[-1] - tramo[0] >= 1.5 and (mejor is None or len(tramo) > len(mejor)):
                mejor = tramo
            ini = i
    return (mejor[0] - 0.05, mejor[-1] + 0.05) if mejor else defecto


def plano_de(objs, t, rot, cache):
    """Escaleras en diagonal (modelos 47, 90, 103, 135 del nivel 0): el suelo de verdad, muestreado en 5 x 5 puntos,
    se ajusta a un plano inclinado. Devuelve (a, b, c) con altura = c + a·x + b·z (x, z de -1 a 1 en la casilla,
    m sobre la altura de la casilla) o None si es llano o no parece un plano."""
    k = (t, rot)
    if k in cache:
        return cache[k]
    out = None
    tris = _tris_suelo(objs, t, rot)
    if tris:
        pts = [(px, pz) for px in (-864, -432, 0, 432, 864) for pz in (-864, -432, 0, 432, 864)]
        bajo, alto = _banda_escalera(tris, (-2.5, 2.0))
        hs = [_suelo_en(tris, px, pz, bajo, alto) for px, pz in pts]
        if None not in hs:
            import numpy as np
            P = np.array(pts, float) / 1024.0
            A = np.c_[P, np.ones(len(P))]
            h = np.array(hs)
            sol = np.linalg.lstsq(A, h, rcond=None)[0]
            rms = float(np.sqrt(np.mean((A @ sol - h) ** 2)))
            if math.hypot(sol[0], sol[1]) > 0.25 and rms < 0.3:
                out = (float(sol[0]), float(sol[1]), float(sol[2]))
    cache[k] = out
    return out


def rampa_de(objs, t, rot, cache):
    """Si el modelo de casilla es una escalera o una rampa: (dirección de subida N/S/E/W, altura del lado bajo,
    altura del lado alto) en m sobre la altura de la casilla, medidas en el suelo de verdad del modelo (cerca del
    centro de cada lado). Si no, None. N = hacia +y del editor (el +z del PS1), E = hacia +x."""
    k = (t, rot)
    if k in cache:
        return cache[k]
    tris = _tris_suelo(objs, t, rot)
    out = None
    if tris:
        m = 1024 - 160
        bajo, alto = _banda_escalera(tris, (-2.5, 2.0))
        h = {lado: _suelo_en(tris, px, pz, bajo, alto)
             for lado, (px, pz) in {"E": (m, 0), "W": (-m, 0), "N": (0, m), "S": (0, -m)}.items()}
        if None not in h.values():
            dx, dz = h["E"] - h["W"], h["N"] - h["S"]
            if abs(dx) >= PASO_RAMPA and abs(dz) < PASO_RAMPA / 2 and abs(dx) <= 3.6:
                out = ("E", h["W"], h["E"]) if dx > 0 else ("W", h["E"], h["W"])
            elif abs(dz) >= PASO_RAMPA and abs(dx) < PASO_RAMPA / 2 and abs(dz) <= 3.6:
                out = ("N", h["S"], h["N"]) if dz > 0 else ("S", h["N"], h["S"])
    cache[k] = out
    return out


def rejilla_kf1(entradas, rtmd, nivel):
    """King's Field (KF2 japonés): cada casilla tiene dos capas (modelo, altura, giro, colisión, flags).
    Se queda la capa que tiene suelo (la segunda si las dos lo tienen); sin suelo: vacío si solo hay tapas
    horizontales (agua, cielo), roca si hay paredes o nada."""
    import kf2_tex
    e = entradas[3 * nivel]
    if not e or struct.unpack_from("<I", e, 0)[0] != 64000:
        raise ValueError(f"El nivel {nivel} no tiene la rejilla de 80 x 80")
    objs = kf2_tex.objetos_tmd(rtmd[nivel])
    tipos = _tipos_casilla(objs)
    g = e[4:4 + 64000]
    celdas = {}
    cache_rampas, cache_suelo, cache_planos = {}, {}, {}
    for z in range(N_KF2):
        for x in range(N_KF2):
            c = g[(z * N_KF2 + x) * 10:(z * N_KF2 + x) * 10 + 10]
            capas = [(c[5], c[6], c[7] & 3), (c[0], c[1], c[2] & 3)]
            elegida = next(((t, h, r) for t, h, r in capas if t < len(tipos) and tipos[t][0]), None)
            if not elegida:
                # una escalera que no empieza a la altura de la casilla (el caracol de la torre del nivel 0: cada
                # casilla sube 2,5 m más arriba que la anterior): también se anda
                elegida = next(((t, h, r) for t, h, r in capas if t < len(objs) and objs[t][1]
                                and _banda_escalera(_tris_suelo(objs, t, r), None)), None)
            if elegida:
                t, h, r = elegida
                te = tipos[t][1]
                celdas[(x, z)] = {"tex": t, "h": h, "forma": 0, "techo_h": h + te if te else None}
                rampa = rampa_de(objs, t, r, cache_rampas)
                if rampa:
                    celdas[(x, z)]["rampa"] = rampa
                else:
                    plano = plano_de(objs, t, r, cache_planos)
                    if plano:
                        celdas[(x, z)]["plano"] = plano
                    else:
                        celdas[(x, z)]["dh"] = suelo_de(objs, t, cache_suelo)
            else:
                # agua poco profunda: el modelo tiene la superficie del agua y, menos de 1,3 m por debajo, un suelo
                # (los bancos de arena del nivel 0: agua a +7,81 m y arena a +7,03): se anda por la arena
                somero = None
                for t, hh, r in capas:
                    if t >= len(objs) or not objs[t][1]:
                        continue
                    niveles = sorted({round(max(a[1], b[1], cc[1]), 2) for a, b, cc in _tris_suelo(objs, t, r)})
                    if len(niveles) >= 2 and niveles[-1] - niveles[-2] <= 1.3:
                        somero = (t, hh, niveles[-2])
                        break
                if somero:
                    t, hh, dh = somero
                    celdas[(x, z)] = {"tex": t, "h": hh, "forma": 0, "techo_h": None, "dh": dh, "somero": True}
                    continue
                hay = [t for t, _, _ in capas if t < len(tipos)]
                vacio = bool(hay) and not any(tipos[t][2] for t in hay)
                celdas[(x, z)] = {"tex": hay[0] if hay else 255, "h": c[6], "forma": 255, "vacio": vacio}
                if not vacio and hay:
                    # lo más alto de sus modelos (m): un pozo o un hueco con agua tiene paredes (los lados del hueco)
                    # pero no sube por encima del suelo de al lado: no es roca, es un agujero
                    topes = [hh * ALTURA_M + max(-v[1] for v in objs[t][0]) * ESCALA_KF
                             for t, hh, _ in capas if t < len(objs) and objs[t][0]]
                    if topes:
                        celdas[(x, z)]["tope_m"] = max(topes)
    # rellanos: casillas sin suelo a su altura pero con un suelo llano a la altura del lado de una escalera vecina (las
    # esquinas del caracol de la torre del nivel 0): se andan a esa altura
    def lado_de(cel, lado):
        if cel.get("rampa"):
            d, lo, hi = cel["rampa"]
            op = {"E": "W", "W": "E", "N": "S", "S": "N"}[d]
            return hi if lado == d else lo if lado == op else None
        if cel.get("rellano"):
            return cel["dh"]
        return None
    VEC = {(1, 0): ("E", "W"), (-1, 0): ("W", "E"), (0, 1): ("N", "S"), (0, -1): ("S", "N")}
    pendientes = [(x, z) for z in range(N_KF2) for x in range(N_KF2)
                  if (x, z) in celdas and celdas[(x, z)]["forma"] == 255]
    while pendientes:        # un rellano puede llevar a otro (lo alto de la torre)
        nuevos = []
        for (x, z) in pendientes:
            cel = celdas.get((x, z))
            if not cel or cel["forma"] != 255:
                continue
            c = g[(z * N_KF2 + x) * 10:(z * N_KF2 + x) * 10 + 10]
            objetivos = []
            for (dx, dz), (lado_mio, lado_suyo) in VEC.items():
                v = celdas.get((x + dx, z + dz))
                if v and v["forma"] != 255:
                    hl = lado_de(v, lado_suyo)
                    if hl is not None:
                        objetivos.append((v["h"] * ALTURA_M + hl, lado_mio))
            if not objetivos:
                continue
            for t, hh, r in ((c[5], c[6], c[7] & 3), (c[0], c[1], c[2] & 3)):
                if t >= len(objs) or not objs[t][1]:
                    continue
                tris = _tris_suelo(objs, t, r)
                centro = _suelo_en(tris, 0, 0, -30.0, 30.0)
                if centro is None:
                    continue
                if any(abs(hh * ALTURA_M + centro - obj) <= 0.5 for obj, _ in objetivos):
                    celdas[(x, z)] = {"tex": t, "h": hh, "forma": 0, "techo_h": None, "dh": centro, "rellano": True}
                    nuevos += [(x + dx, z + dz) for dx, dz in VEC]
                    break
        pendientes = [k for k in dict.fromkeys(nuevos) if k in celdas and celdas[k]["forma"] == 255]
    # los agujeros: sin suelo y con lo más alto de sus modelos a menos de 1 m sobre el suelo de las vecinas
    for (x, z), cel in celdas.items():
        if cel.get("tope_m") is None:
            continue
        suelos = [celdas[v]["h"] * ALTURA_M + celdas[v].get("dh", 0.0)
                  for v in ((x + dx, z + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1))
                  if v in celdas and celdas[v]["forma"] != 255]
        if suelos and cel["tope_m"] <= max(suelos) + 1.0:
            cel["vacio"] = True
            cel["hoyo"] = True
    return celdas


def _ruido(n, paso, semilla):
    """Ruido suave (n x n): valores al azar cada `paso` casillas, interpolados."""
    import numpy as np
    rng = np.random.default_rng(semilla)
    g = rng.uniform(-1, 1, (n // paso + 3, n // paso + 3))
    y, x = np.mgrid[0:n, 0:n] / paso
    i, j = x.astype(int), y.astype(int)
    fx, fy = x - i, y - j
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    return ((g[j, i] * (1 - fx) + g[j, i + 1] * fx) * (1 - fy) + (g[j + 1, i] * (1 - fx) + g[j + 1, i + 1] * fx) * fy)


def colores_vertice(n, pad, andable, roca):
    """Colores de vértice del terreno (0xRRGGBB, 128 = sin cambio):
      - sombra donde el suelo toca la pared (y, como la pared toma el color del suelo abajo, la pared se
        oscurece de abajo arriba)
      - manchas de tono (cálido, frío, verdoso) y de luz en el suelo, suaves, para que no sea todo igual."""
    import numpy as np
    m = n + 1
    occ = np.zeros((m, m))
    for vj in range(m):
        for vi in range(m):
            x, z = vi - pad, vj - pad
            alrededor = [(x + dx, z + dz) for dx in (-1, 0) for dz in (-1, 0)]
            occ[vj, vi] = sum(1 for k in alrededor if k in roca) / 4.0
    # la sombra se abre un poco (una casilla) con una media de los vecinos, sin aclarar el pie de la pared
    blur = occ.copy()
    blur[1:-1, 1:-1] = (occ[1:-1, 1:-1] * 4 + occ[:-2, 1:-1] + occ[2:, 1:-1] + occ[1:-1, :-2] + occ[1:-1, 2:]) / 8
    sombra = 1.0 - 0.75 * np.maximum(occ, blur * 0.75)
    calido, frio, verde = _ruido(m, 7, 1), _ruido(m, 9, 2), _ruido(m, 11, 3)
    luz = 1.0 + 0.16 * _ruido(m, 5, 4) + 0.07 * _ruido(m, 2, 5)
    r = luz * (1 + 0.16 * calido - 0.10 * frio - 0.06 * verde)
    g = luz * (1 + 0.03 * calido - 0.02 * frio + 0.12 * verde)
    b = luz * (1 - 0.14 * calido + 0.15 * frio - 0.08 * verde)
    out = []
    for c in (r, g, b):
        out.append(np.clip(np.round(128 * c * sombra), 0, 255).astype(int))
    return [int((out[0][vj, vi] << 16) | (out[1][vj, vi] << 8) | out[2][vj, vi]) for vj in range(m) for vi in range(m)]


def convertir(celdas, interior=None, aspecto=None, imagenes=None):
    """aspecto: {objeto de casilla: {'suelo'|'pared'|'techo': nombre de textura}} (kf2_tex.texturas_nivel) para
    usar las texturas del propio King's Field II; sin él, las del 4 repartidas por frecuencia."""
    andable = {k for k, c in celdas.items() if c["forma"] != 255}
    if not andable:
        raise ValueError("Ese nivel no tiene casillas")
    con_techo = {k for k in andable if celdas[k].get("techo_h")}
    techos_propios = bool(con_techo) or any("techo_h" in c for c in celdas.values())
    if techos_propios:            # King's Field (KF2 japonés): cada casilla dice si tiene techo y a qué altura
        interior = len(con_techo) > len(andable) / 2
    if interior is None:          # casi todo a dos casillas o menos de la roca = pasillos y salas: interior
        cerca = sum(1 for (x, z) in andable
                    if any((x + dx, z + dz) not in andable for dx in range(-2, 3) for dz in range(-2, 3)))
        interior = cerca / len(andable) > 0.5
    n = N_EDITOR
    pad = (n - N_KF2) // 2
    h0 = min(celdas[k]["h"] for k in andable)
    # la altura del suelo de verdad (rejilla_kf1: "dh", lo que el suelo del modelo queda sobre la casilla)
    alt = {k: (celdas[k]["h"] - h0) * ALTURA_M + celdas[k].get("dh", 0.0) for k in andable}

    # texturas: las de KF2 por frecuencia -> las del 4
    freq = collections.Counter(celdas[k]["tex"] for k in andable)
    suelos = SUELOS_INTERIOR if interior else SUELOS_EXTERIOR
    tex_de = {t: suelos[i % len(suelos)] for i, (t, _) in enumerate(freq.most_common())}

    # casillas al borde de un desnivel grande (un escalón o un risco, no una rampa): van como bloques planos
    # para que el corte sea una pared recta; el resto es terreno con los vértices compartidos (rampas suaves)
    # escaleras y rampas de los modelos (rejilla_kf1): casillas "esc" del editor (colisión en rampa), con el lado bajo
    # y el alto medidos en el suelo de verdad; para comparar con las vecinas cuenta la altura de su lado
    rampas = {k: celdas[k]["rampa"] for k in andable if celdas[k].get("rampa")}
    print(f"Escaleras y rampas (colisión en rampa, medidas en el modelo): {len(rampas)} casillas")
    LADO = {(1, 0): "E", (-1, 0): "W", (0, 1): "N", (0, -1): "S"}
    OPUESTO = {"E": "W", "W": "E", "N": "S", "S": "N"}

    planos = {k: celdas[k]["plano"] for k in andable if celdas[k].get("plano")}
    if planos:
        print(f"Escaleras en diagonal (colisión inclinada, ajustada al modelo): {len(planos)} casillas")
    PUNTO_LADO = {"E": (1, 0), "W": (-1, 0), "N": (0, 1), "S": (0, -1)}

    def alt_lado(k, lado):
        if k in planos:
            a, b, c0 = planos[k]
            px, pz = PUNTO_LADO[lado]
            return alt[k] + c0 + a * px + b * pz
        if k not in rampas:
            return alt[k]
        d, lo, hi = rampas[k]
        return alt[k] + (hi if lado == d else lo if lado == OPUESTO[d] else (lo + hi) / 2)
    escalon = {(x, z) for (x, z) in andable if (x, z) not in rampas and (x, z) not in planos
               and any((x + dx, z + dz) in alt
                       and abs(alt_lado((x + dx, z + dz), OPUESTO[LADO[(dx, dz)]]) - alt[(x, z)]) > SALTO_RECTO
                       for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))}
    alturas = [0.0] * ((n + 1) * (n + 1))
    texturas = [0] * (n * n)
    for vj in range(n + 1):
        for vi in range(n + 1):
            x, z = vi - pad, vj - pad
            # si el vértice es la esquina de una escalera, manda la escalera (su lado bajo o alto): si no, la media
            # con el terreno de al lado deja un escalón de más de 0,35 m al pie, que es pared en la colisión
            esquinas = []
            for dx in (-1, 0):
                for dz in (-1, 0):
                    k = (x + dx, z + dz)
                    if k in rampas:
                        d, lo, hi = rampas[k]
                        alto = {"E": dx == -1, "W": dx == 0, "N": dz == -1, "S": dz == 0}[d]
                        esquinas.append(alt[k] + (hi if alto else lo))
                    elif k in planos:
                        a, b, c0 = planos[k]
                        esquinas.append(alt[k] + c0 + a * (1 if dx == -1 else -1) + b * (1 if dz == -1 else -1))
            if esquinas:
                alturas[vj * (n + 1) + vi] = round(sum(esquinas) / len(esquinas), 3)
                continue
            vecinas = [alt[(x + dx, z + dz)] for dx in (-1, 0) for dz in (-1, 0)
                       if (x + dx, z + dz) in alt and (x + dx, z + dz) not in escalon
                       and (x + dx, z + dz) not in rampas]
            if not vecinas:
                vecinas = [alt[(x + dx, z + dz)] for dx in (-1, 0) for dz in (-1, 0) if (x + dx, z + dz) in alt]
            if vecinas:
                alturas[vj * (n + 1) + vi] = round(sum(vecinas) / len(vecinas), 3)
    mapa_celdas = {}

    def techo(x, z):     # sobre el vértice más alto de la casilla, redondeado hacia arriba al paso
        if techos_propios:
            th = celdas[(x, z)].get("techo_h")       # a pasos de PASO_TECHO_KF1: menos faldones entre techos
            return math.ceil((th - h0) * ALTURA_M / PASO_TECHO_KF1 - 1e-6) * PASO_TECHO_KF1 if th else None
        i, j = x + pad, z + pad
        alto = max(alturas[jj * (n + 1) + ii] for ii in (i, i + 1) for jj in (j, j + 1))
        return math.ceil((alto + ALTO_TECHO) / PASO_TECHO - 1e-6) * PASO_TECHO
    pared = "sillar" if interior else "roca"
    def asp(k, clase, defecto):
        if not aspecto:
            return defecto
        d = aspecto.get(celdas[k]["tex"], {}) if k in celdas else {}
        return d.get(clase) or d.get("suelo") or d.get("pared") or defecto
    for (x, z) in andable:
        i, j = x + pad, z + pad
        texturas[j * n + i] = PALETA.index(asp((x, z), "suelo", tex_de[celdas[(x, z)]["tex"]]))
        tiene_techo = (interior and not techos_propios) or (techos_propios and techo(x, z) is not None)
        if (x, z) in rampas:
            d, lo, hi = rampas[(x, z)]
            b = {"esc": [d, round(alt[(x, z)] + lo, 3), round(alt[(x, z)] + hi, 3)],
                 "tex": asp((x, z), "suelo", tex_de[celdas[(x, z)]["tex"]]),
                 "pared": asp((x, z), "pared", "sillar" if interior else "roca")}
            if tiene_techo:
                b.update(techo=techo(x, z), ttex=asp((x, z), "techo", "muro"))
            mapa_celdas[f"{i},{j}"] = b
        elif (x, z) in escalon:
            b = {"f": round(alt[(x, z)], 3), "tex": asp((x, z), "suelo", tex_de[celdas[(x, z)]["tex"]]),
                 "pared": asp((x, z), "pared", "sillar" if interior else "roca")}
            if tiene_techo:
                b.update(techo=techo(x, z), ttex=asp((x, z), "techo", "muro"))
            mapa_celdas[f"{i},{j}"] = b
        elif tiene_techo:
            mapa_celdas[f"{i},{j}"] = {"terreno": True, "techo": techo(x, z), "ttex": asp((x, z), "techo", "muro")}
    # la roca que toca algo andable es un bloque: la pared
    for (x, z), c in celdas.items():
        if (x, z) in andable or c.get("vacio"):        # el vacío (agua, cielo) se queda abierto: niebla
            continue
        toca = [alt[(x + dx, z + dz)] for dx in (-1, 0, 1) for dz in (-1, 0, 1) if (x + dx, z + dz) in alt]
        if not toca:
            continue
        i, j = x + pad, z + pad
        techos_v = [techo(x + dx, z + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1) if (x + dx, z + dz) in alt]
        cubierta = (interior and not techos_propios) or (bool(techos_v) and all(t is not None for t in techos_v))
        if cubierta:      # hasta el techo más alto de las casillas que toca
            f = max(techos_v)
        else:
            f = max(toca) + ALTO_RISCO
        if aspecto:       # la pared de la roca: la que llevan las casillas andables que la tocan
            votos = collections.Counter(asp((x + dx, z + dz), "pared", pared)
                                        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)) if (x + dx, z + dz) in alt)
            pr = votos.most_common(1)[0][0] if votos else pared
        else:
            pr = pared
        # la parte alta de la pared más clara que el pie (que toma la sombra del suelo): degradado de abajo arriba
        mapa_celdas[f"{i},{j}"] = {"f": round(f, 3), "tex": pr, "pared": pr, "cc": [CLARO_PARED] * 4}
        if cubierta:      # su cara de arriba queda a la altura del techo: no se ve desde dentro
            mapa_celdas[f"{i},{j}"]["tapa"] = False

    colores = colores_vertice(n, pad, andable, {k for k, c in celdas.items() if k not in andable and not c.get("vacio")})
    for (x, z) in escalon:      # los bloques llevan el mismo color de vértice que tendría el terreno
        i, j = x + pad, z + pad
        mapa_celdas[f"{i},{j}"]["cc"] = [colores[jj * (n + 1) + ii] for ii, jj in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))]
    # inicio: la casilla andable más rodeada de andables cerca del centro
    def puntos(k):
        x, z = k
        alrededor = sum((x + dx, z + dz) in andable for dx in range(-2, 3) for dz in range(-2, 3))
        return alrededor * 10 - math.hypot(x - 40, z - 40)
    # ...dentro de la zona conectada más grande (casillas unidas sin saltos de más de SALTO_ZONA m): si no, se
    # puede empezar en una sala cerrada (el nivel 7 tiene zonas que solo se unen por caídas de 13 m)
    zona_de, zonas = {}, []
    for k0 in andable:
        if k0 in zona_de:
            continue
        pila, zona = [k0], [k0]
        zona_de[k0] = len(zonas)
        while pila:
            x, z = pila.pop()
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                v = (x + dx, z + dz)
                if v in andable and v not in zona_de and abs(alt[v] - alt[(x, z)]) <= SALTO_ZONA:
                    zona_de[v] = len(zonas)
                    pila.append(v)
                    zona.append(v)
        zonas.append(zona)
    mayor = max(zonas, key=len)
    sx, sz = max(mayor, key=puntos)
    print(f"Inicio en la zona conectada más grande: {len(mayor)} de {len(andable)} casillas andables "
          f"({len(zonas)} zonas separadas por desniveles)")
    ox = oy = -n * CELDA / 2
    m = {
        "version": 2, "n": n, "celda": CELDA, "origen": [ox, oy], "alturas": alturas, "texturas": texturas,
        "paleta": PALETA, "celdas": mapa_celdas, "colores": colores, "paredes": None,
        "pared_terreno": pared, "borde_prof": 10, "cubierta": False, "grosor_techo": 0.6,
        "objetos": [], "inicio": {"x": ox + (sx + pad + 0.5) * CELDA, "y": oy + (sz + pad + 0.5) * CELDA, "rumbo": 0},
        "guardado": None, "items": [], "enemigos": [],
        "niebla": [40, 44, 52] if interior else [150, 160, 170], "niebla_k": 400000 if interior else 1400000,
        "barandilla": False,     # sin pared invisible en el borde del agua: se puede caer al mar (y morir)
        "kf_base": {"h0": h0, "pad": pad},
        # cielo de nubes si hay casillas al aire libre (sin techo) o si es un exterior
        "cielo": (not interior) or (techos_propios and len(con_techo) < len(andable)),
    }
    if imagenes:
        from PIL import Image
        m["texturas_kf2"] = {}
        for nombre, img in imagenes.items():
            b = io.BytesIO()
            Image.fromarray(img).save(b, "PNG")
            m["texturas_kf2"][nombre] = base64.b64encode(b.getvalue()).decode()
        m["escala_tex"] = CELDA          # una textura de KF2 por casilla, como en el original
        m["pared_terreno"] = collections.Counter(c.get("pared") for c in mapa_celdas.values()
                                                 if c.get("pared")).most_common(1)[0][0] if mapa_celdas else pared
    return m, interior, len(andable)


def poner_enemigos_kf1(m, arch, nivel):
    """Enemigos y objetos del nivel original, con sus equivalentes del 4 (kf1_objetos.py)."""
    import kf1_objetos
    import kf2_tex
    objs_nivel = kf2_tex.objetos_tmd(arch["RTMD.T"][nivel])
    tipos = _tipos_casilla(objs_nivel)
    cache_suelo = {}
    g = arch["FDAT.T"][3 * nivel][4:4 + 64000]
    h0, pad = m["kf_base"]["h0"], m["kf_base"]["pad"]

    def altura_capa(x, z, capa):
        if not (0 <= x < N_KF2 and 0 <= z < N_KF2):
            return None
        c = g[(z * N_KF2 + x) * 10:(z * N_KF2 + x) * 10 + 10]
        # la capa 0 de los enemigos y objetos es la segunda de la casilla (bytes 5-7) y la 1 la primera: así cae
        # sobre suelo casi todo (nivel 0: 154 de 159 en la capa 0 y 47 de 56 en la 1; al revés, 5 y 9)
        t, h = (c[5], c[6]) if capa == 0 else (c[0], c[1])
        if t < len(tipos) and tipos[t][0]:
            return (h - h0) * ALTURA_M + suelo_de(objs_nivel, t, cache_suelo)
        return None
    celdas = rejilla_kf1(arch["FDAT.T"], arch["RTMD.T"], nivel)

    def vecinos(x, z):
        return {(dx, dz): celdas.get((x + dx, z + dz), {}).get("forma", 255) != 255
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))}

    def techo_de(x, z):
        c = celdas.get((x, z), {})
        if c.get("techo_h") is None or c.get("forma", 255) == 255:
            return None
        return (c["techo_h"] - c["h"]) * ALTURA_M
    ox, oy = m["origen"]
    def es_agua(x, z):                   # el mar y el agua honda (casillas sin suelo): ahí van los peces
        return "vacio" in celdas.get((x, z), {})
    enemigos, items, resto, res = kf1_objetos.para_editor(arch["FDAT.T"], nivel, pad, ox, oy, CELDA, altura_capa,
                                                          vecinos, techo_de, es_agua)
    m["enemigos"], m["items"] = enemigos, items
    m["kf_objetos"] = resto              # cofres (con lo que llevan dentro), puertas y paredes que se abren
    print("Enemigos: " + (", ".join(f"{n} {t}" for t, n in res["enemigos"].most_common()) or "ninguno"))
    print(f"  tipos del 4 usados: {', '.join(res['tipos_kf4'])}"
          + (f"  (otros cambiados: {res['cambiados']})" if res["cambiados"] else ""))
    if res["sin_equivalente"]:
        print(f"  sin equivalente (no se ponen): modelos {dict(res['sin_equivalente'])}")
    print(f"Objetos por el suelo: {res['objetos']}  cofres: {res['cofres']}  puertas: {res['puertas']}  "
          f"paredes secretas: {res['secretas']}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    if sys.argv[2].lower().endswith(".json") or not sys.argv[2].lstrip("-").isdigit():
        # sin número de nivel: el mismo nivel que ya está portado en ese .json (PROBAR_NEGRO.bat)
        previo = sys.argv[2] if sys.argv[2].lower().endswith(".json") else "mapa_torre.json"
        try:
            with open(previo) as f:
                km = json.load(f).get("kf_malla") or {}
            nivel = int(km["nivel"])
        except (OSError, ValueError, KeyError):
            print(f"No sé qué nivel portar: escríbelo (p. ej. 1) o porta antes uno con JUGAR_KF2.bat")
            return 1
        sys.argv.insert(2, str(nivel))
        print(f"Se vuelve a portar el nivel {nivel}")
    ruta, nivel = sys.argv[1], int(sys.argv[2])
    salida = next((a for a in sys.argv[3:] if not a.startswith("--")), f"kf2_nivel{nivel:02d}.json")
    interior = True if "--interior" in sys.argv else False if "--exterior" in sys.argv else None
    if "--sin-rampas" in sys.argv:        # prueba: los escalones como antes (pared a partir de 1 m)
        global SALTO_RECTO
        SALTO_RECTO = 1.0
    arch = leer_archivos(ruta)
    juego = juego_de(arch)
    if juego == "kf1":
        if "RTMD.T" not in arch:
            raise FileNotFoundError("Falta RTMD.T")
        celdas = rejilla_kf1(arch["FDAT.T"], arch["RTMD.T"], nivel)
    else:
        celdas = rejilla(arch["FDAT.T"], nivel)
    aspecto = imagenes = None
    if "RTIM.T" in arch and "RTMD.T" in arch and "--texturas-kf4" not in sys.argv:
        import kf2_tex
        usos = [c["tex"] for c in celdas.values() if c["forma"] != 255]
        aspecto, imagenes = kf2_tex.texturas_nivel(arch["FDAT.T"], arch["RTIM.T"], arch["RTMD.T"], nivel, usos,
                                                   BASE_VRAM[juego])
    m, interior, n_and = convertir(celdas, interior, aspecto, imagenes)
    if "--cuadrado" not in sys.argv and "RTIM.T" in arch and "RTMD.T" in arch:
        # la geometría real de cada casilla (kf_malla.py); la rejilla de arriba queda para el editor y la altura
        m["kf_malla"] = {"ruta": os.path.abspath(ruta), "juego": juego, "nivel": nivel, **m["kf_base"]}
    if juego == "kf1" and "--sin-enemigos" not in sys.argv:
        poner_enemigos_kf1(m, arch, nivel)
    print(f"Juego: {'King' + chr(39) + 's Field (KF2 japonés)' if juego == 'kf1' else 'King' + chr(39) + 's Field II USA (KF3 japonés)'}")
    with open(salida, "w") as f:
        json.dump(m, f)
    print(f"Nivel {nivel}: {n_and} casillas andables, {'interior' if interior else 'exterior'}, "
          f"{'con las texturas de King' + chr(39) + 's Field II' if imagenes else 'con texturas del 4'} -> {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
