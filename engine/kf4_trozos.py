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
    dz_esperada = float(salida.get("z", 0.0)) - float(llegada.get("z", 0.0))

    def pasillo(iguales):
        """Lo que casa unido a la casilla de la salida (o a una de al lado): el pasillo repetido."""
        ini = next((k for k in [s] + [(s[0] + i, s[1] + j) for i in (-1, 0, 1) for j in (-1, 0, 1)]
                    if k in iguales), None)
        if ini is None:
            return set()
        M_, pila = {ini}, [ini]
        while pila:
            a_, b_ = pila.pop()
            for k in ((a_ + 1, b_), (a_ - 1, b_), (a_, b_ + 1), (a_, b_ - 1)):
                if k in iguales and k not in M_:
                    M_.add(k)
                    pila.append(k)
        return M_
    mejor = None
    for di in range(-6, 7):
        for dj in range(-6, 7):
            dx = round(base[0] / CELDA) + di
            dy = round(base[1] / CELDA) + dj
            dzs = collections.Counter()
            for c in zona0:
                k = (c[0] + dx, c[1] + dy)
                if k in H1:
                    for a_ in H0[c]:
                        for b_ in H1[k]:
                            if abs((a_ - b_) - dz_esperada) <= 3.0:     # a la altura de la salida y la llegada
                                dzs[round(a_ - b_, 1)] += 1
            if not dzs:
                continue
            dz = dzs.most_common(1)[0][0]
            iguales = {c for c in zona0 if (c[0] + dx, c[1] + dy) in H1
                       and _iguales(H0[c], H1[(c[0] + dx, c[1] + dy)], dz)}
            M_ = pasillo(iguales)
            # el pasillo más largo que pasa por la salida; a igualdad, el más cerca de donde dicen la salida y la
            # llegada (antes contaba todo lo que casaba en 20 m y a veces ganaba otro sitio parecido)
            clave = (len(M_), -(abs(di) + abs(dj)))
            if M_ and (mejor is None or clave > mejor[0]):
                mejor = (clave, dx, dy, dz, M_, len(iguales))
    if not mejor or len(mejor[4]) < 4:
        return None, None
    _, dx, dy, dz, M, n = mejor
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


def _cercanas(celdas, otras, B=8):
    """{casilla: (distancia, la más cercana de otras)} (en casillas). Sin numpy ni scipy (en Windows no siempre
    están): las otras se reparten en cubos de B x B casillas y se miran los cubos en anillos crecientes."""
    if not otras:
        return {c: (1e9, None) for c in celdas}
    cubos = collections.defaultdict(list)
    for o in otras:
        cubos[(o[0] // B, o[1] // B)].append(o)
    xs = [k[0] for k in cubos]
    ys = [k[1] for k in cubos]
    lim = max(max(xs) - min(xs), max(ys) - min(ys)) + 2
    out = {}
    for c in celdas:
        cx, cy = c[0] // B, c[1] // B
        mejor, cual = None, None
        r = 0
        while r <= lim + abs(cx - xs[0]) + abs(cy - ys[0]):
            for i in range(cx - r, cx + r + 1):
                for j in range(cy - r, cy + r + 1):
                    if max(abs(i - cx), abs(j - cy)) != r:
                        continue
                    for o in cubos.get((i, j), ()):
                        d = (o[0] - c[0]) ** 2 + (o[1] - c[1]) ** 2
                        if mejor is None or d < mejor or (d == mejor and o < cual):
                            mejor, cual = d, o
            # lo que quede más allá del anillo r está a más de (r * B) casillas
            if mejor is not None and math.sqrt(mejor) <= r * B:
                break
            r += 1
        out[c] = (math.sqrt(mejor), cual) if mejor is not None else (1e9, None)
    return out


def _distancias(celdas, otras):
    """{casilla: distancia (en casillas) a la más cercana de otras}."""
    return {c: d for c, (d, _) in _cercanas(celdas, otras).items()}


class Nivel:
    """Lo que hace falta de un nivel para trocearlo: sus casillas de suelo (alturas), cuáles están al aire libre,
    y de quién es cada tira de geometría: de la casilla de suelo a la que mira (las paredes van con la sala que las
    ve, no con la roca de detrás: si no, al no estar cargado el trozo de al lado faltaban paredes) o, si no mira a
    ningún suelo, de la casilla de suelo más cercana."""

    def __init__(self, v):
        self.v = v
        self.H = dict(alturas(v))
        techo = collections.defaultdict(list)
        candidatas = set()
        for by_tex in v.geo.render.values():
            for seqs in by_tex.values():
                for s in seqs:
                    p = _centro([q[0] for q in s])
                    n = s[0][3] if len(s[0]) > 3 and s[0][3] else (0.0, 0.0, 0.0)
                    if n[2] < -0.6:
                        techo[celda(p)].append(p[2])
                    candidatas.add(self._mira(p, n))
                    candidatas.add(celda(p))
        for cc in v.geo.coll.values():
            for polys in cc.values():
                for q in polys:
                    candidatas.add(celda(_centro(q)))
        self.aire = {c for c, zs in self.H.items() if not (c in techo and min(techo[c]) > min(zs) + 0.5)}
        suelo = set(self.H)
        self._cerca = {c: o for c, (_, o) in _cercanas(candidatas - suelo, suelo).items()}
        self.todas = candidatas | suelo
        self.w = collections.Counter()
        for by_tex in v.geo.render.values():
            for seqs in by_tex.values():
                for s in seqs:
                    self.w[self.dueno_tira(s)] += len(s)
        for cc in v.geo.coll.values():
            for polys in cc.values():
                for q in polys:
                    self.w[self.dueno_poli(q)] += len(q)

    @staticmethod
    def _mira(p, n):
        return celda((p[0] + n[0] * 0.6, p[1] + n[1] * 0.6))

    def dueno_celda(self, c):
        if c in self.H:
            return c
        o = self._cerca.get(c)
        if o is None:
            o = _cercanas([c], set(self.H))[c][1]
            self._cerca[c] = o
        return o

    def dueno_tira(self, s):
        p = _centro([q[0] for q in s])
        n = s[0][3] if len(s[0]) > 3 and s[0][3] else (0.0, 0.0, 0.0)
        m = self._mira(p, n)
        if m in self.H and abs(n[2]) < 0.6:
            return m                       # una pared: con el suelo al que mira
        return self.dueno_celda(celda(p))

    def dueno_poli(self, q):
        return self.dueno_celda(celda(_centro(q)))

    def dueno_punto(self, p):
        return self.dueno_celda(celda(p))


def particion(nivel, presupuesto, excluir=frozenset(), inicio=None, primeras=None):
    """Las casillas de suelo del nivel (menos las excluidas) en trozos de peso <= presupuesto, cortando por donde
    menos se ve, como los mapas del IV: nunca al aire libre (cada zona al aire libre unida va entera en un trozo,
    desde fuera se ve lejos) y bajo techo por los pasillos estrechos.
    Se crece desde una entrada (la zona al aire libre más grande, o la casilla de inicio): por capas de distancia
    andando, y el trozo acaba en la capa con menos pasos a la siguiente (el pasillo más estrecho) de las que le
    dejan un tamaño razonable; lo que queda detrás se separa en ramas, cada una con su entrada, y se sigue igual."""
    H = nivel.H
    nodos = set(H) - set(excluir)
    w = {c: nivel.w.get(c, 0) + 1 for c in nodos}
    ady = {c: [] for c in nodos}
    for c in nodos:
        for k in VECINAS4:
            d = (c[0] + k[0], c[1] + k[1])
            if d in nodos and _pasa(H[c], H[d]):
                ady[c].append(d)
    # grupos: cada zona al aire libre unida es un grupo que no se parte; cada casilla bajo techo, el suyo
    grupo = {}
    grupos = []
    for c in sorted(nodos):
        if c in grupo:
            continue
        g = len(grupos)
        if c in nivel.aire:
            miembros, pila = [c], [c]
            grupo[c] = g
            while pila:
                x = pila.pop()
                for d in ady[x]:
                    if d in nivel.aire and d not in grupo:
                        grupo[d] = g
                        miembros.append(d)
                        pila.append(d)
        else:
            grupo[c] = g
            miembros = [c]
        grupos.append(miembros)
    gw = [sum(w[c] for c in m) for m in grupos]
    gady = [set() for _ in grupos]
    for c in nodos:
        for d in ady[c]:
            if grupo[d] != grupo[c]:
                gady[grupo[c]].add(grupo[d])
    paso = collections.Counter()           # pasos entre grupos (cuántas casillas se tocan)
    for c in nodos:
        for d in ady[c]:
            if grupo[d] != grupo[c]:
                paso[(grupo[c], grupo[d])] += 1

    libres = set(range(len(grupos)))
    trozos = []

    def crecer(entrada):
        """Un trozo desde los grupos de entrada (libres); devuelve sus grupos."""
        dist = {g: 0 for g in entrada}
        capas = [list(entrada)]
        while True:
            sig = []
            for g in capas[-1]:
                for h in gady[g]:
                    if h in libres and h not in dist:
                        dist[h] = len(capas)
                        sig.append(h)
            if not sig:
                break
            capas.append(sig)
        pesos = [sum(gw[g] for g in capa) for capa in capas]
        total = sum(pesos)
        if total <= presupuesto:
            return set(dist)
        mejor, acum = None, 0
        for k, capa in enumerate(capas[:-1]):
            acum += pesos[k]
            if acum > presupuesto and k > 0:
                break
            if acum < presupuesto * 0.5 and k + 1 < len(capas) and acum + pesos[k + 1] <= presupuesto:
                continue          # (muy pequeño: un trozo que solo es la boca de un pasillo no sirve)
            siguiente = set(capas[k + 1])
            corte = sum(paso[(g, h)] for g in capa for h in gady[g] if h in siguiente)
            clave = (corte, -acum)
            if mejor is None or clave < mejor[0]:
                mejor = (clave, k)
        k = mejor[1] if mejor else 0
        return {g for g, d_ in dist.items() if d_ <= k}

    def ramas(conj):
        quedan = set(conj)
        out = []
        while quedan:
            g0 = min(quedan)
            comp, pila = {g0}, [g0]
            while pila:
                x = pila.pop()
                for h in gady[x]:
                    if h in quedan and h not in comp:
                        comp.add(h)
                        pila.append(h)
            out.append(comp)
            quedan -= comp
        return out

    # la primera entrada: la zona al aire libre más grande (o el grupo del inicio)
    aire = [g for g, m in enumerate(grupos) if m[0] in nivel.aire]
    primeros = {grupo[c] for c in (primeras or ()) if c in grupo}
    if primeros:
        # (el nivel 1: todo lo que toca el pasillo del enlace en un mismo trozo, para que el enlace tenga un solo
        # vecino en ese nivel)
        primero = None
    elif aire:
        primero = max(aire, key=lambda g: gw[g])
    elif inicio is not None and nivel.dueno_punto(inicio) in grupo:
        primero = grupo[nivel.dueno_punto(inicio)]
    else:
        primero = max(range(len(grupos)), key=lambda g: gw[g])
    pendientes = [primeros or {primero}]
    while libres:
        if not pendientes:
            # lo que no se puede alcanzar andando desde lo hecho (saltos, bajadas): desde su grupo más pesado
            pendientes.append({max(libres, key=lambda g: gw[g])})
        entrada = pendientes.pop(0) & libres
        if not entrada:
            continue
        if all(grupos[g][0] in nivel.aire for g in entrada) and not trozos:
            # lo de fuera, entero y solo: un mapa (desde fuera se ve lejos; dentro la niebla corta la vista)
            t = set(entrada)
        else:
            t = crecer(entrada)
        libres -= t
        trozos.append(t)
        # lo que queda detrás de este trozo, rama por rama, con su entrada (lo que toca al trozo)
        cerca = {h for g in t for h in gady[g] if h in libres}
        for rama in ramas(libres):
            e = rama & cerca
            if e:
                pendientes.append(e)
    # los trozos muy pequeños, con el vecino más pequeño que los admita
    def vecinos_de(t):
        return {i for i, u in enumerate(trozos) if u is not t and any(h in u for g in t for h in gady[g])}
    cambio = True
    while cambio:
        cambio = False
        for t in sorted(trozos, key=lambda u: sum(gw[g] for g in u)):
            pt = sum(gw[g] for g in t)
            if pt >= presupuesto * 0.3:
                continue
            opciones = [i for i in vecinos_de(t) if sum(gw[g] for g in trozos[i]) + pt <= presupuesto]
            if not opciones and len(trozos) > 1:
                # suelto (sin vecino andando): con el trozo más cercano en línea recta que lo admita
                yo = {c for g in t for c in grupos[g]}
                resto = [(i, {c for g in u for c in grupos[g]}) for i, u in enumerate(trozos) if u is not t]
                resto = [(min(_cercanas(list(yo)[:50], cs).values())[0], i) for i, cs in resto
                         if sum(gw[g] for g in trozos[i]) + pt <= presupuesto]
                opciones = [min(resto)[1]] if resto else []
            if opciones:
                i = min(opciones, key=lambda i: sum(gw[g] for g in trozos[i]))
                trozos[i] |= t
                trozos.remove(t)
                cambio = True
                break
    return [{c for g in t for c in grupos[g]} for t in trozos]


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


ZONA_PASOS = 10     # casillas andando (25 m) desde la puerta a un vecino en las que el juego ya lo va cargando


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
        cand = [x for x in cand if any(v_ == 0 for v_ in x[3].values())]     # solo los que se alcanzan andando
        a.vecinos = [(b, xyz) for b, xyz, _, _, _ in cand]
        a.puertas = {b.nombre: sum(1 for v_ in camino.values() if v_ == 0) for b, _, _, camino, _ in cand}
        a.zonas = {}
        for c in a.celdas:
            if not cand:
                a.zonas[c] = -1
                continue
            por_camino = [(cand[i][3][c], cand[i][4], i) for i in range(len(cand)) if c in cand[i][3]]
            pasos, _, j = min(por_camino) if por_camino else (None, 0, 0)
            if pasos is not None and pasos <= ZONA_PASOS:
                a.zonas[c] = j * 2 + (1 if pasos <= 1 else 0)
            else:
                # lejos de todas las puertas: no pide nada (se queda cargado lo que hubiera). Antes cada casilla pedía
                # siempre su vecino más cercano y, andando por el medio de un trozo con dos vecinos, el juego cargaba
                # uno, luego el otro, luego el primero... sin parar (tirones y la escalera del enlace sin llegar)
                a.zonas[c] = -1


MARGEN = 3          # casillas de geometría de alrededor que lleva repetida cada trozo (7,5 m)


def geo_de(nivel, trozo):
    """Un Geo con solo las tiras de las casillas del trozo, cada registro partido por zonas (la clave del trozo de
    geometría lleva la zona al final: ("G", i, j, zona))."""
    import kf4_valle
    valle = nivel.v
    g = kf4_valle.Geo()
    g.trozos = valle.geo.trozos
    if hasattr(valle.geo, "banda"):
        g.banda = valle.geo.banda
    # lo que se ve desde el trozo: su geometría y, repetida, la de alrededor (MARGEN casillas): las fachadas que dan
    # a su zona, el principio de la sala de al lado... Así, mientras el vecino no está cargado, no se ve el vacío
    # nada más pasar la frontera. Repetida en los dos mapas es la misma geometría en el mismo sitio.
    area = {c for c in nivel.todas if nivel.dueno_celda(c) in trozo.celdas}
    amplia = set()
    m = getattr(trozo, "margen", MARGEN)
    for (x, y) in area:
        for i in range(-m, m + 1):
            for j in range(-m, m + 1):
                amplia.add((x + i, y + j))
    fuera = amplia - area
    cerca = {c: o for c, (_, o) in _cercanas(fuera, trozo.celdas).items()} if fuera else {}
    trozo.repetidas = 0
    for ch, by_tex in valle.geo.render.items():
        for tex, seqs in by_tex.items():
            for s in seqs:
                c = nivel.dueno_tira(s)
                if c in trozo.celdas:
                    g.render[tuple(ch) + (trozo.zonas.get(c, -1), c not in nivel.aire)][tex].append(s)
                    continue
                k = celda(_centro([q[0] for q in s]))
                if k in amplia:
                    o = c if c in trozo.celdas else cerca.get(k)
                    g.render[tuple(ch) + (trozo.zonas.get(o, -1), c not in nivel.aire)][tex].append(s)
                    trozo.repetidas += 1
    for ch, cc in valle.geo.coll.items():
        for kind, polys in cc.items():
            for q in polys:
                c = nivel.dueno_poli(q)
                if c in trozo.celdas:
                    k = tuple(ch) + (trozo.zonas.get(c, -1), c not in nivel.aire)
                    g.coll[k].setdefault(kind, [])
                    g.coll[k][kind].append(q)
    return g


def vista(nivel, trozo):
    """Una copia ligera del nivel con solo lo de las casillas del trozo (geometría, bichos, gente, objetos, fuentes,
    piedra de guardado) y sin cambios de nivel con fundido (ya no hacen falta)."""
    valle = nivel.v
    v = copy.copy(valle)
    dentro = lambda p: nivel.dueno_punto(p) in trozo.celdas
    v.geo = geo_de(nivel, trozo)
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


# ======================= Cortes a mano (cortes_niveles.html) =======================
# La página CORTES_NIVELES.html (la escribe cada generación sin fundido, con los datos de los dos niveles dentro)
# enseña cada nivel desde arriba con sus trozos; se pintan a mano y se guarda cortes.json junto a kf4_valle.py.
# La siguiente generación usa esos trozos (si casan con el nivel y caben de dos en dos en memoria).

def _caja(nivel):
    cs = set(nivel.H) | set(getattr(nivel, "todas", ()))
    xs = [c[0] for c in cs]
    ys = [c[1] for c in cs]
    return min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


def datos_nivel(nivel, trozos, auto, excluir, inicio=None, salida=None):
    """Lo que la página necesita de un nivel (listas por casilla, fila a fila de sur a norte)."""
    x0, y0, w, h = _caja(nivel)
    n = w * h
    alt, pisos, aire, roca, peso, enl, tro, aut = ([-999] * n, [0] * n, [0] * n, [0] * n, [0] * n, [0] * n,
                                                   [0] * n, [0] * n)
    k_ = lambda c: (c[1] - y0) * w + (c[0] - x0)
    for c in getattr(nivel, "todas", ()):
        if 0 <= c[0] - x0 < w and 0 <= c[1] - y0 < h:
            roca[k_(c)] = 1
    for c, zs in nivel.H.items():
        i = k_(c)
        alt[i] = int(round(max(zs) * 10))
        pisos[i] = len({round(z) for z in zs})
        aire[i] = 1 if c in nivel.aire else 0
        peso[i] = int(nivel.w.get(c, 0))
        enl[i] = 1 if c in excluir else 0
    for j, t in enumerate(trozos):
        for c in t:
            tro[k_(c)] = j + 1
    for j, t in enumerate(auto):
        for c in t:
            aut[k_(c)] = j + 1
    rel = lambda p: [celda(p)[0] - x0, celda(p)[1] - y0] if p else None
    return {"x0": x0, "y0": y0, "w": w, "h": h, "suelos": len(nivel.H), "alt": alt, "pisos": pisos, "aire": aire,
            "roca": roca, "peso": peso, "enlace": enl, "trozo": tro, "auto": aut, "inicio": rel(inicio),
            "salida": rel(salida), "k": 30.0}


def escribir_html(ruta, datos):
    import json
    import os
    plantilla = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cortes_niveles.html")
    with open(plantilla, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("/*DATOS*/null", json.dumps(datos, separators=(",", ":")))
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)


def leer_cortes(ruta, clave, nivel, excluir):
    """Los trozos pintados a mano para un nivel (lista de conjuntos de casillas de suelo), o (None, motivo)."""
    import json
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)["niveles"][clave]
    except (OSError, ValueError, KeyError) as e:
        return None, f"no se puede leer ({e})"
    if d.get("suelos") != len(nivel.H):
        return None, "es de otra versión del nivel (no casan las casillas)"
    x0, y0, w, h = d["x0"], d["y0"], d["w"], d["h"]
    t = d["trozo"]
    pintadas = {}
    for c in nivel.H:
        if c in excluir:
            continue
        i, j = c[0] - x0, c[1] - y0
        v = t[j * w + i] if 0 <= i < w and 0 <= j < h else 0
        if v > 0:
            pintadas[c] = v
    if not pintadas:
        return None, "no tiene nada pintado"
    sin = [c for c in nivel.H if c not in excluir and c not in pintadas]
    if sin:
        cerca = _cercanas(sin, set(pintadas))
        for c in sin:
            pintadas[c] = pintadas[cerca[c][1]]
    grupos = collections.defaultdict(set)
    for c, v in pintadas.items():
        grupos[v].add(c)
    return [grupos[v] for v in sorted(grupos)], None


# ======================= Lo que se ve desde cada sitio (como el IV) =======================
# El IV no dibuja todo lo cargado: cada registro lleva en +0x38 su grupo (una "sala": varios registros pueden
# compartirlo) y el mapa una tabla de bloques de 0x40 bytes, uno por grupo: los grupos de ese mapa que se ven
# estando en él (256 bits) y hasta 16 parejas (número de mapa, grupo) del mapa vecino que también se ven
# (Map_TestFlagBlockBit; el bloque es el del grupo del suelo que pisas). Lo que no está en el bloque no se dibuja
# (func_00112BD0), ni sus bichos ni sus objetos. 099, por ejemplo: desde su grupo 2 se ven los grupos 2, 3 y 14 del
# 008. Los trozos llevaban los bloques de 099 tal cual (parejas con los mapas 98, 8 y 5): el trozo vecino, aunque
# estuviera cargado, no se dibujaba nunca hasta pisarlo. Ahora cada trozo lleva los suyos: sus grupos son los
# trozos de geometría (de unos 20 m), y desde cada uno se ve lo que se alcanza andando a VISTA_PASOS casillas (las
# salas de al lado, no el piso de arriba ni lo que hay detrás de la roca), en el trozo y en sus vecinos; al aire
# libre, todo el trozo.
VISTA_PASOS = 18       # casillas andando (45 m; la niebla de dentro cierra a 30 m)


def grupos(nivel, trozos):
    """Los grupos de cada trozo de un nivel: t.grupo {trozo de geometría: número} y t.celdas_grupo {número:
    casillas de suelo}. El 0 es "siempre se ve" (lo que no tiene suelo propio: agua, lo repetido de alrededor)."""
    de = {}
    for t in trozos:
        t.grupo, t.celdas_grupo = {}, collections.defaultdict(set)
        for c in t.celdas:
            de[c] = t

    def apunta(ch, c):
        t = de.get(c)
        if t is None:
            return
        g = t.grupo.get(ch)
        if g is None:
            g = len(t.grupo) + 1
            if g > 254:
                g = 0              # (no pasa: 254 trozos de geometría en un solo mapa)
            t.grupo[ch] = g
        if g:
            t.celdas_grupo[g].add(c)
    for ch, by_tex in nivel.v.geo.render.items():
        for seqs in by_tex.values():
            for s in seqs:
                apunta(tuple(ch), nivel.dueno_tira(s))
    for ch, cc in nivel.v.geo.coll.items():
        for polys in cc.values():
            for q in polys:
                apunta(tuple(ch), nivel.dueno_poli(q))


def visibilidad(trozos, desfase):
    """t.bloques: los bloques de flags de cada trozo (uno por grupo, 0x40 bytes)."""
    import struct
    for a in trozos:
        n = max([0] + list(getattr(a, "celdas_grupo", {}).keys())) + 1
        # las puertas a cada vecino, en las coordenadas de a: casilla de a -> casillas de b al lado
        puertas = []
        for b, _ in a.vecinos:
            mover, dz, _ = desfase(a, b)
            hb = {mover(c): (c, [z + dz for z in zs]) for c, zs in b.alturas.items()}
            pu = collections.defaultdict(list)
            for c, za in a.alturas.items():
                for k in VECINAS4:
                    m = (c[0] + k[0], c[1] + k[1])
                    if m in hb and _pasa(za, hb[m][1]):
                        pu[c].append(hb[m][0])
            g_de_b = {c: g for g, cs in b.celdas_grupo.items() for c in cs}
            puertas.append((b, pu, g_de_b))
        g_de_a = {c: g for g, cs in a.celdas_grupo.items() for c in cs}
        aire_a = {g for g, cs in a.celdas_grupo.items() if any(c in getattr(a, "aire", ()) for c in cs)}
        bloques = bytearray()
        for g in range(n):
            bits = {0}
            pares = []                                   # (distancia, mapa, grupo)
            if g == 0 or g in aire_a:
                bits |= set(range(n))
            ini = a.celdas_grupo.get(g, set()) if g else set(a.alturas)
            dist = {c: 0 for c in ini}
            frente = list(ini)
            vistos_b = {}
            for paso in range(VISTA_PASOS + 1):
                sig = []
                for c in frente:
                    if c in g_de_a:
                        bits.add(g_de_a[c])
                    for i, (b, pu, g_de_b) in enumerate(puertas):
                        for cb in pu.get(c, ()):
                            if (i, cb) not in vistos_b:
                                vistos_b[(i, cb)] = paso
                    for k in VECINAS4:
                        m = (c[0] + k[0], c[1] + k[1])
                        if m in a.alturas and m not in dist and _pasa(a.alturas[c], a.alturas[m]):
                            dist[m] = paso + 1
                            sig.append(m)
                frente = sig
                if not frente:
                    break
            # dentro de cada vecino, desde sus casillas de puerta, lo que queda de camino
            for i, (b, pu, g_de_b) in enumerate(puertas):
                ini_b = {cb: p for (j, cb), p in vistos_b.items() if j == i}
                db = dict(ini_b)
                frente = sorted(ini_b, key=lambda c: ini_b[c])
                while frente:
                    sig = []
                    for c in frente:
                        if c in g_de_b:
                            pares.append((db[c], b.mapa, g_de_b[c]))
                        if db[c] >= VISTA_PASOS:
                            continue
                        for k in VECINAS4:
                            m = (c[0] + k[0], c[1] + k[1])
                            if m in b.alturas and m not in db and _pasa(b.alturas[c], b.alturas[m]):
                                db[m] = db[c] + 1
                                sig.append(m)
                    frente = sig
            # parejas: lo siempre visible de cada vecino y los grupos más cerca, hasta 16
            lista = [(b.mapa, 0) for b, _, _ in puertas]
            for _, mapa, gb in sorted(pares):
                if (mapa, gb) not in lista:
                    lista.append((mapa, gb))
            lista = lista[:16]
            blk = bytearray(0x40)
            for bit in bits:
                if bit < 256:
                    blk[bit // 8] |= 1 << (bit % 8)
            for i in range(16):
                t_, v_ = lista[i] if i < len(lista) else (255, 255)
                blk[0x20 + i] = t_ & 0xFF
                blk[0x30 + i] = v_ & 0xFF
            bloques += blk
        a.bloques = bytes(bloques)
        a.grupos_vistos = n
