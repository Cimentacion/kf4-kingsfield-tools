#!/usr/bin/env python3
"""
kf4_trozos.py - Los niveles portados sin pantalla de carga: cada nivel se trocea en varios mapas del 4 que el juego
carga solos en segundo plano, como hace el IV con los suyos (map/map_load.c de kfiv-decomp).

Cómo lo hace el IV: cada registro (trozo de geometría) del mapa lleva en +0x3A el índice de un "origen" de la tabla
de vecinos (32 entradas de 0x10 bytes detrás de los bloques de flags: x, y, z float y el número de mapa en +12).
Mientras el jugador pisa un registro con origen, MapLoad_Update carga ese mapa en el otro hueco de memoria, sin
parar el juego, desplazado -(x, y, z). Cuando el suelo que pisa es del otro mapa, Map_MakeCurrent lo hace el mapa
actual (mueve todo por el desplazamiento y arranca su guion). +0x39 a 1: si el vecino no ha terminado de cargar al
pisar ese registro, el juego lo termina allí mismo (sin fundido, un momento quieto). Los dos mapas tienen que caber
juntos en la memoria de mapas (MapLoad_OpenFile: si no, el juego se cuelga): cada trozo ocupa la geometría de su
parte más lo fijo de 099 (texturas, objetos, sonido: unos 2,8 MB).

Cómo se trocea:
  - por casillas del nivel (2,5 m): cada tira de geometría y de colisión va al trozo de la casilla de su centro;
  - un nivel en rebanadas a lo largo de su eje largo, con el mismo peso (vértices y puntos de colisión) en cada una:
    así cada trozo toca como mucho otros dos y nunca hacen falta tres cargados a la vez;
  - entre dos niveles del King's Field el pasillo de la salida está repetido en los dos (el mismo suelo, a otra
    altura y en otro sitio de su rejilla): se busca el desplazamiento que los hace coincidir y ese pasillo va en un
    trozo propio (el "enlace", con la geometría del nivel de arriba). Así los dos niveles nunca están cargados a la
    vez fuera del pasillo: el resto de un nivel se solapa en el espacio con el otro;
  - cada registro pide el vecino más cercano a sus casillas, y los que tocan la frontera lo exigen (+0x39).
"""

import collections
import copy
import math

CELDA = 2.5


def celda(p):
    return (math.floor(p[0] / CELDA + 1e-6), math.floor(p[1] / CELDA + 1e-6))


def _centro(pts):
    n = len(pts)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)


def pesos(valle):
    """Counter casilla -> peso (vértices de dibujo + puntos de colisión de las tiras de su centro)."""
    w = collections.Counter()
    for by_tex in valle.geo.render.values():
        for seqs in by_tex.values():
            for s in seqs:
                w[celda(_centro([v[0] for v in s]))] += len(s)
    for c in valle.geo.coll.values():
        for kind, polys in c.items():
            for q in polys:
                w[celda(_centro(q))] += len(q)
    return w


def alturas(valle):
    """{casilla: [alturas de suelo]} (los centros de los polígonos de suelo de la colisión)."""
    h = collections.defaultdict(list)
    for c in valle.geo.coll.values():
        for q in c.get("floor", []):
            p = _centro(q)
            h[celda(p)].append(p[2])
    return h


def _iguales(za, zb, dz, tol=0.35):
    """Los mismos suelos (con dz de diferencia), sin ninguno de más en ninguno de los dos."""
    return (all(any(abs(a - (b + dz)) < tol for b in zb) for a in za)
            and all(any(abs(a - (b + dz)) < tol for a in za) for b in zb))


def enlace(v0, v1, salida, llegada, radio=20.0, log=None):
    """El pasillo repetido entre el nivel v0 (su salida al otro) y v1 (su llegada desde v0).
    -> (D, M): D = (dx, dy, dz) tal que un punto p del nivel 0 es p + D en el nivel 1; M = casillas del nivel 0 del
    pasillo (las que tienen exactamente los mismos suelos en los dos), o None si no casan."""
    H0, H1 = alturas(v0), alturas(v1)
    s = celda((salida["x"], salida["y"]))
    base = (llegada["x"] - salida["x"], llegada["y"] - salida["y"])
    r = int(radio / CELDA)
    zona0 = [(s[0] + i, s[1] + j) for i in range(-r, r + 1) for j in range(-r, r + 1) if (s[0] + i, s[1] + j) in H0]
    mejor = None
    for di in range(-8, 9):
        for dj in range(-8, 9):
            dx = round(base[0] / CELDA) + di
            dy = round(base[1] / CELDA) + dj
            dzs = collections.Counter()
            for c in zona0:
                k = (c[0] + dx, c[1] + dy)
                if k in H1:
                    for a in H0[c]:
                        for b in H1[k]:
                            dzs[round(a - b, 1)] += 1
            if not dzs:
                continue
            dz = dzs.most_common(1)[0][0]
            n = sum(1 for c in zona0 if (c[0] + dx, c[1] + dy) in H1 and _iguales(H0[c], H1[(c[0] + dx, c[1] + dy)], dz))
            if mejor is None or n > mejor[0]:
                mejor = (n, dx, dy, dz)
    if not mejor or mejor[0] < 4:
        return None, None
    n, dx, dy, dz = mejor
    iguales = {c for c in zona0 if (c[0] + dx, c[1] + dy) in H1 and _iguales(H0[c], H1[(c[0] + dx, c[1] + dy)], dz)}
    # el pasillo: lo que casa unido a la casilla de la salida (o a la que casa más cerca de ella)
    ini = s if s in iguales else min(iguales, key=lambda c: (c[0] - s[0]) ** 2 + (c[1] - s[1]) ** 2)
    M, pila = {ini}, [ini]
    while pila:
        a, b = pila.pop()
        for k in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
            if k in iguales and k not in M:
                M.add(k)
                pila.append(k)
    # la dz exacta: la media de las diferencias del pasillo
    difs = [a - b for c in M for a in H0[c] for b in H1[(c[0] + dx, c[1] + dy)] if abs(a - b - dz) < 0.35]
    dz = sum(difs) / len(difs) if difs else dz
    D = (dx * CELDA, dy * CELDA, -dz)
    if log is not None:
        log.append(f"Enlace entre niveles: {len(M)} casillas del pasillo iguales en los dos ({n} en {radio:.0f} m); "
                   f"el nivel siguiente está {D[0]:+.2f}, {D[1]:+.2f}, {D[2]:+.2f} m más allá")
    return D, M


def rebanadas(w, n, celdas):
    """n conjuntos de casillas (de las dadas), en rebanadas del mismo peso a lo largo del eje más largo."""
    celdas = list(celdas)
    if n <= 1 or len(celdas) < n:
        return [set(celdas)]
    xs = [c[0] for c in celdas]
    ys = [c[1] for c in celdas]
    eje = 0 if max(xs) - min(xs) >= max(ys) - min(ys) else 1
    filas = collections.Counter()
    for c in celdas:
        filas[c[eje]] += max(1, w.get(c, 0))
    orden = sorted(filas)
    total = sum(filas.values())
    cortes, acum, k = [], 0, 1
    for f in orden:
        acum += filas[f]
        if k < n and acum >= total * k / n:
            cortes.append(f)
            k += 1
    trozos = [set() for _ in range(n)]
    for c in celdas:
        i = sum(1 for t in cortes if c[eje] > t)
        trozos[i].add(c)
    return [t for t in trozos if t]


def _distancias(celdas, otras, B=8):
    """{casilla: distancia (en casillas) a la más cercana de otras}. Sin numpy ni scipy (en Windows no siempre
    están): las otras se reparten en cubos de B x B casillas y se miran los cubos en anillos crecientes."""
    if not otras:
        return {c: 1e9 for c in celdas}
    cubos = collections.defaultdict(list)
    for o in otras:
        cubos[(o[0] // B, o[1] // B)].append(o)
    xs = [k[0] for k in cubos]
    ys = [k[1] for k in cubos]
    lim = max(max(xs) - min(xs), max(ys) - min(ys)) + 2
    out = {}
    for c in celdas:
        cx, cy = c[0] // B, c[1] // B
        mejor = None
        r = 0
        while r <= lim:
            for i in range(cx - r, cx + r + 1):
                for j in range(cy - r, cy + r + 1):
                    if max(abs(i - cx), abs(j - cy)) != r:
                        continue
                    for o in cubos.get((i, j), ()):
                        d = (o[0] - c[0]) ** 2 + (o[1] - c[1]) ** 2
                        if mejor is None or d < mejor:
                            mejor = d
            # lo que quede más allá del anillo r está a más de (r * B) casillas
            if mejor is not None and math.sqrt(mejor) <= r * B:
                break
            r += 1
        out[c] = math.sqrt(mejor) if mejor is not None else 1e9
    return out


class Trozo:
    def __init__(self, nivel, celdas, nombre, alturas=None):
        self.nivel = nivel          # índice del nivel cuya geometría lleva
        self.celdas = set(celdas)   # en las coordenadas de su nivel
        self.nombre = nombre
        self.alturas = {c: alturas[c] for c in self.celdas if c in alturas} if alturas else {}
        self.mapa = None            # número de mapa del 4
        self.vecinos = []           # [(trozo, desfase en cm (x, y, z) del juego)]
        self.zonas = {}             # casilla -> zona (índice de vecino * 2 + exige)


PASO = 1.6       # m de altura entre dos casillas de suelo que se pueden andar de una a otra (escalones, rampas)
VECINAS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _pasa(za, zb):
    return any(abs(a - b) <= PASO for a in za for b in zb)


def vecinos_y_zonas(trozos, puede, desfase, toque=1.5):
    """Para cada trozo: sus vecinos y la zona de cada casilla (qué vecino pide el juego mientras la pisas).
    Vecinos: los trozos cuyas casillas tocan las suyas (en las coordenadas de su nivel; si no se ven, no hace falta
    tenerlos cargados). La zona de una casilla es el vecino al que se llega antes andando: el camino por suelo
    (casillas con suelo a menos de PASO de altura de la de al lado) hasta su "puerta" (una casilla propia que se pisa
    seguida de una del vecino); a igualdad, el del mismo nivel. Las casillas de la puerta, y las de al lado, lo exigen
    (+0x39). Si no hay camino a ninguna puerta, el vecino más cercano en línea recta, sin exigirlo.
    puede(a, b): si pueden ser vecinos; desfase(a, b) -> (mover_celda, dz, xyz): mover_celda pasa una casilla de b a
    las coordenadas de a, dz la diferencia de alturas (altura en a = altura en b + dz) y xyz el desfase de la tabla
    de vecinos de a para cargar b."""
    for a in trozos:
        cand = []
        for b in trozos:
            if b is a or not puede(a, b):
                continue
            mover, dz, xyz = desfase(a, b)
            otras = {mover(c) for c in b.celdas}
            d = _distancias(a.celdas, otras)
            if min(d.values()) > toque:
                continue
            hb = {mover(c): [z + dz for z in zs] for c, zs in b.alturas.items()}
            puertas = {c for c, za in a.alturas.items() for k in VECINAS4
                       if (c[0] + k[0], c[1] + k[1]) in hb and _pasa(za, hb[(c[0] + k[0], c[1] + k[1])])}
            # camino andando desde las puertas, por las casillas con suelo del trozo
            camino = {c: 0 for c in puertas}
            frente = list(puertas)
            while frente:
                sig = []
                for c in frente:
                    for k in VECINAS4:
                        n = (c[0] + k[0], c[1] + k[1])
                        if n in a.alturas and n not in camino and _pasa(a.alturas[c], a.alturas[n]):
                            camino[n] = camino[c] + 1
                            sig.append(n)
                frente = sig
            cand.append((b, xyz, d, camino, 0 if b.nivel == a.nivel else 1))
        a.vecinos = [(b, xyz) for b, xyz, _, _, _ in cand]
        a.puertas = {b.nombre: sum(1 for v_ in camino.values() if v_ == 0) for b, _, _, camino, _ in cand}
        a.zonas = {}
        for c in a.celdas:
            if not cand:
                a.zonas[c] = -1
                continue
            por_camino = [(cand[i][3][c], cand[i][4], i) for i in range(len(cand)) if c in cand[i][3]]
            if por_camino:
                pasos, _, j = min(por_camino)
                a.zonas[c] = j * 2 + (1 if pasos <= 1 else 0)
            else:
                j = min(range(len(cand)), key=lambda i: (cand[i][2][c], cand[i][4]))
                a.zonas[c] = j * 2


def geo_de(valle, trozo):
    """Un Geo con solo las tiras de las casillas del trozo, cada registro partido por zonas (la clave del trozo de
    geometría lleva la zona al final: ("G", i, j, zona))."""
    import kf4_valle
    g = kf4_valle.Geo()
    g.trozos = valle.geo.trozos
    if hasattr(valle.geo, "banda"):
        g.banda = valle.geo.banda
    for ch, by_tex in valle.geo.render.items():
        for tex, seqs in by_tex.items():
            for s in seqs:
                c = celda(_centro([v[0] for v in s]))
                if c in trozo.celdas:
                    g.render[tuple(ch) + (trozo.zonas[c],)][tex].append(s)
    for ch, cc in valle.geo.coll.items():
        for kind, polys in cc.items():
            for q in polys:
                c = celda(_centro(q))
                if c in trozo.celdas:
                    k = tuple(ch) + (trozo.zonas[c],)
                    g.coll[k].setdefault(kind, [])
                    g.coll[k][kind].append(q)
    return g


def vista(valle, trozo):
    """Una copia ligera del nivel con solo lo de las casillas del trozo (geometría, bichos, gente, objetos, fuentes,
    piedra de guardado) y sin cambios de nivel con fundido (ya no hacen falta)."""
    v = copy.copy(valle)
    dentro = lambda p: celda(p) in trozo.celdas
    v.geo = geo_de(valle, trozo)
    v.enemigos = [(t, p) for t, p in valle.enemigos if dentro(p)]
    v.objetos = [(i, p) for i, p in getattr(valle, "objetos", []) if dentro(p)]
    v.kf_objetos = [o for o in getattr(valle, "kf_objetos", []) if dentro(o["pos"])]
    v.kf_npcs = [n for n in getattr(valle, "kf_npcs", []) if dentro(n["pos"])]
    v.kf_fuentes = [p for p in getattr(valle, "kf_fuentes", []) if dentro(p)]
    g = getattr(valle, "guardado", None)
    v.guardado = g if g and dentro(g) else None
    v.kf_salidas = []
    v.kf_llegadas = {}
    v._trozo = trozo
    return v
