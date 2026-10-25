#!/usr/bin/env python3
"""
kf4_prologo.py - Prólogo de "La Torre" (King's Field IV, estilo Tower Dungeon).

Empiezas dentro de una casita de piedra, en lo alto de un risco con una aldea de tres casas y ruinas de
columnas. Un puente de arcos sobre la niebla lleva a la barbacana, a los pies de una torre inmensa que
sube hasta perderse. Usa las texturas del propio 099 (Palacio de Oath: sillares, losas, columnas).

Coordenadas en metros, Z hacia arriba (las mismas que kf4_valle). La torre se sube: esto es la parte
más baja. Lo usa kf4_valle.py con --zona prologo (la opción por defecto).
"""

import math
import random

import kf4_valle as kv
from kf4_valle import Geo, Ruido, add, sub, mul, norm, cross, clamp

# ---- texturas de 099 (TBP, CBP) ----
SILLAR = (0x36C0, 0x3D50)        # sillares grandes
MURO = (0x3080, 0x3D47)          # muro de bloques
LOSA_IRR = (0x3540, 0x3D4E)      # losas irregulares
BANDA = (0x2FA0, 0x3D45)         # piedra con una franja (cornisa)
ESTRIA = (0x2FE0, 0x3D48)        # columna estriada
ESTRIA2 = (0x33C0, 0x3D4B)       # columnas en fila
NICHO = (0x3120, 0x3D57)         # muro con una ventana estrecha
ROCA = (0x2F80, 0x3D44)          # roca
ROCA2 = (0x2E40, 0x3D41)         # roca gris
ROCA_MUSGO = (0x3720, 0x3D55)    # roca con musgo
LADR = (0x3640, 0x3D51)          # ladrillo pequeño
PIEDRA_LISA = (0x36E0, 0x3D54)   # piedra lisa clara
GRAVA = (0x39C0, 0x3D46)         # grava / suelo
MADERA = (0x2F40, 0x3D43)        # tablas oscuras
FRISO = (0x3440, 0x3D56)         # friso

SOL = norm((0.32, -0.55, 0.77))   # luz de día: el sol a la espalda de quien mira la torre
CELDA = 2.5


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class LuzDia:
    """Luz horneada de día con mucho contraste (piedra clara al sol, sombras casi negras)."""

    def __init__(self, ruido):
        self.r = ruido
        self.fuentes = []          # (centro, radio, fuerza): luz cálida dentro de las casas

    def piedra(self, p, n, ao=1.0, interior=0.0):
        d = max(0.0, dot(n, SOL))
        cielo = 0.5 + 0.5 * n[2]
        var = 0.88 + 0.24 * self.r.v(p[0] * 0.21 + p[2] * 0.13, p[1] * 0.21, 17)
        # mucho contraste, como el dibujo de Nihei: piedra casi blanca al sol, sombra casi negra
        k = (0.10 + 1.55 * d ** 0.8 + 0.20 * cielo) * ao * var
        if interior > 0:
            k = k * (1.0 - interior) + 0.10 * interior * var * ao
        r, g, b = 128 * k * 1.03, 128 * k * 1.0, 128 * k * 0.95
        for (c, rad, fu) in self.fuentes:
            dd = math.dist(p, c)
            if dd < rad:
                w = fu * (1.0 - dd / rad) ** 2 * ao
                r += 128 * w * 1.25
                g += 128 * w * 0.95
                b += 128 * w * 0.62
        # niebla de abajo: la roca se aclara hacia el mar de niebla
        if p[2] < -10:
            t = clamp((-10 - p[2]) / 120.0, 0, 1) * 0.55
            r, g, b = r * (1 - t) + 150 * t, g * (1 - t) + 158 * t, b * (1 - t) + 170 * t
        return (clamp(r, 0, 255), clamp(g, 0, 255), clamp(b, 0, 255))


class Prologo:
    tex_fuente = "099"
    niebla = (214, 218, 224)           # cielo despejado, casi blanco, y niebla clara
    niebla_k = 1400000.0               # la niebla empieza más lejos que en el valle

    def __init__(self, semilla):
        self.semilla = semilla
        self.rng = random.Random(semilla)
        self.ruido = Ruido(semilla)
        self.luz = LuzDia(self.ruido)
        self.geo = Geo()
        self.enemigos = []
        self.objetos = []
        self.guardado = None
        self.casas = []
        # compatibilidad con los avisos de kf4_valle.main
        self.ventanas, self.puertas, self.spawns_pos = [], [], []
        # trazado
        self.puente_y0, self.puente_y1 = 30.0, 172.0
        self.puente_z0, self.puente_z1 = 0.0, 3.0
        self.puente_ancho = 5.0           # múltiplo de la rejilla del risco (2,5 m): sin suelos solapados
        self.barb_y0 = self.puente_y1           # fachada de la barbacana
        self.barb_fondo = 12.0
        self.torre_r = 115.0             # inmensa: el muro casi parece plano desde el puente
        # la cara de la torre queda dentro del muro del fondo de la barbacana
        self.torre_c = (0.0, self.barb_y0 + self.barb_fondo - 0.5 + self.torre_r)

    # ======================= utilidades =======================
    def q(self, ch, tex, a, b, c, d, uv, n=None, ao=(1, 1, 1, 1), interior=0.0, k=1.0, cerca=True):
        if n is None:
            n = norm(cross(sub(b, a), sub(d, a)))
        cols = [mul(self.luz.piedra(p, n, ao_, interior), k) for p, ao_ in zip((a, b, c, d), ao)]
        self.geo.quad(ch, tex, a, b, c, d, *uv, *cols, n, cerca=cerca)

    def pared(self, ch, tex, p0, p1, z0, z1, esc=4.0, interior=0.0, ao_pie=True, k=1.0, u0=0.0):
        """Cara vertical de p0 a p1 (planta), de z0 a z1. La normal sale a la izquierda de p0->p1."""
        a, b = (p0[0], p0[1], z0), (p1[0], p1[1], z0)
        c, d = (p1[0], p1[1], z1), (p0[0], p0[1], z1)
        largo = math.dist(p0, p1)
        n = norm((-(p1[1] - p0[1]), p1[0] - p0[0], 0.0))
        aob = 0.55 if ao_pie else 1.0
        uv = ((u0 / esc, -z0 / esc), ((u0 + largo) / esc, -z0 / esc), ((u0 + largo) / esc, -z1 / esc),
              (u0 / esc, -z1 / esc))
        self.q(ch, tex, a, b, c, d, uv, n, (aob, aob, 1, 1), interior, k)

    def suelo(self, ch, tex, a, b, c, d, esc=3.0, interior=0.0, ao=(1, 1, 1, 1), k=1.0, coll=True):
        up = (0.0, 0.0, 1.0)
        uv = tuple((p[0] / esc, p[1] / esc) for p in (a, b, c, d))
        self.q(ch, tex, a, b, c, d, uv, up, ao, interior, k)
        if coll:
            self.geo.cquad(ch, "floor", a, b, c, d)

    def muro_coll(self, ch, p0, p1, z0, alto=2.4):
        self.geo.cquad(ch, "wall", (p0[0], p0[1], z0), (p1[0], p1[1], z0), (p1[0], p1[1], z0 + alto),
                       (p0[0], p0[1], z0 + alto))

    def prisma(self, ch, tex, c, r, z0, z1, lados=6, esc=2.0, coll=0.0, roto=0.0, k=1.0, tapa=True, cerca=True):
        """Columna de `lados` caras. coll: alto de la colisión (0 = sin). roto: el tope sale irregular."""
        pts = [(c[0] + r * math.cos(2 * math.pi * i / lados), c[1] + r * math.sin(2 * math.pi * i / lados))
               for i in range(lados)]
        tops = [z1 - roto * self.ruido.v(c[0] * 3 + i, c[1] * 3, 33) for i in range(lados)]
        for i in range(lados):
            p0, p1 = pts[i], pts[(i + 1) % lados]
            a, b = (p0[0], p0[1], z0), (p1[0], p1[1], z0)
            cc, d = (p1[0], p1[1], tops[(i + 1) % lados]), (p0[0], p0[1], tops[i])
            n = norm(((p0[0] + p1[0]) / 2 - c[0], (p0[1] + p1[1]) / 2 - c[1], 0.0))
            uv = ((i / lados * 1.5, -z0 / esc), ((i + 1) / lados * 1.5, -z0 / esc),
                  ((i + 1) / lados * 1.5, -cc[2] / esc), (i / lados * 1.5, -d[2] / esc))
            self.q(ch, tex, a, b, cc, d, uv, n, (0.6, 0.6, 1, 1), 0.0, k, cerca=cerca)
            if coll:
                self.muro_coll(ch, p0, p1, z0 - 0.5, coll)
        if not tapa:
            return
        # tapa (en abanico, como quads degenerados de dos en dos)
        cz = max(tops)
        for i in range(0, lados, 2):
            p0, p1, p2 = pts[i], pts[(i + 1) % lados], pts[(i + 2) % lados]
            a = (c[0], c[1], cz)
            self.q(ch, tex, a, (p0[0], p0[1], tops[i]), (p1[0], p1[1], tops[(i + 1) % lados]),
                   (p2[0], p2[1], tops[(i + 2) % lados]),
                   ((0.5, 0.5), (p0[0] - c[0] + 0.5, p0[1] - c[1] + 0.5), (p1[0] - c[0] + 0.5, p1[1] - c[1] + 0.5),
                    (p2[0] - c[0] + 0.5, p2[1] - c[1] + 0.5)), (0, 0, 1), k=k)

    # ======================= el risco y la aldea =======================
    def radio_risco(self, ang):
        """Borde de la meseta: irregular, alargado hacia el puente (+Y)."""
        base = 27.0 + 5.5 * self.ruido.fbm(math.cos(ang) * 1.3 + 3, math.sin(ang) * 1.3 + 3, 91, 3)
        hacia_puente = max(0.0, math.sin(ang)) ** 6
        return base * (1 - hacia_puente) + 31.0 * hacia_puente

    def dentro(self, x, y):
        r = math.hypot(x, y)
        return r <= self.radio_risco(math.atan2(y, x))

    def al_borde(self, x, y):
        ang = math.atan2(y, x)
        r = self.radio_risco(ang)
        return (r * math.cos(ang), r * math.sin(ang))

    def risco(self):
        ocupado = set()
        for c in self.casas_def:
            for i in range(int(round((c["x1"] - c["x0"]) / CELDA))):
                for j in range(int(round((c["y1"] - c["y0"]) / CELDA))):
                    ocupado.add((round(c["x0"] + i * CELDA, 2), round(c["y0"] + j * CELDA, 2)))
        # bajo el arranque del puente no hay suelo del risco (el tablero empieza en y = 30)
        w = self.puente_ancho / 2
        celdas = {}
        n = 18
        for i in range(-n, n):
            for j in range(-n, n):
                x0, y0 = i * CELDA, j * CELDA
                cx, cy = x0 + CELDA / 2, y0 + CELDA / 2
                if not self.dentro(cx, cy):
                    continue
                if (round(x0, 2), round(y0, 2)) in ocupado:
                    continue
                if -w - 1e-6 <= x0 and x0 + CELDA <= w + 1e-6 and y0 >= self.puente_y0 - 1e-6:
                    continue
                celdas[(i, j)] = (x0, y0)
        esquina = {}

        def punto(x, y):
            k = (round(x, 2), round(y, 2))
            if k not in esquina:
                if self.dentro(x, y):
                    esquina[k] = (x, y, 0.0)
                else:
                    bx, by = self.al_borde(x, y)
                    esquina[k] = (bx, by, 0.0)
            return esquina[k]
        bordes = {}
        for (i, j), (x0, y0) in celdas.items():
            a, b = punto(x0, y0), punto(x0 + CELDA, y0)
            c, d = punto(x0 + CELDA, y0 + CELDA), punto(x0, y0 + CELDA)
            cx, cy = x0 + CELDA / 2, y0 + CELDA / 2
            ch = ("R", int(cx // 20), int(cy // 20))
            tex = LOSA_IRR if self.en_camino(cx, cy) else (GRAVA if self.ruido.v(cx * 0.15, cy * 0.15, 5) > 0.66
                                                             else ROCA_MUSGO)
            self.suelo(ch, tex, a, b, c, d, esc=3.0 if tex == LOSA_IRR else 4.0)
            for (p, q_, vec) in ((a, b, (i, j - 1)), (b, c, (i + 1, j)), (c, d, (i, j + 1)), (d, a, (i - 1, j))):
                if vec in celdas:
                    continue
                vx, vy = vec[0] * CELDA + CELDA / 2, vec[1] * CELDA + CELDA / 2
                if self.dentro(vx, vy):
                    continue        # al lado hay una casa o el puente, no el vacío
                bordes[(p[:2], q_[:2])] = (p, q_, ch)
        # caras del acantilado bajo cada borde suelto (no bajo casas ni bajo el puente)
        niveles = [0.0, -1.2, -3.5, -8.0, -16.0, -30.0, -55.0, -95.0, -160.0, -260.0]
        for (p, q_, ch) in bordes.values():
            xm, ym = (p[0] + q_[0]) / 2, (p[1] + q_[1]) / 2
            filas = []
            for z in niveles:
                fila = []
                for pt in (p, q_):
                    ang = math.atan2(pt[1], pt[0])
                    sal = 0.0 if z == 0 else 1.4 * self.ruido.fbm(ang * 4.0, z * 0.08, 95, 3) - 0.04 * z
                    fila.append((pt[0] + math.cos(ang) * sal, pt[1] + math.sin(ang) * sal, z))
                filas.append(fila)
            for (a, b), (d, c) in zip(filas, filas[1:]):
                largo = math.dist(a[:2], b[:2])
                ang = math.atan2(ym, xm)
                n = (math.cos(ang), math.sin(ang), 0.0)
                e_ = 5.0 if c[2] > -20 else (12.0 if c[2] > -60 else 30.0)
                u0 = ang * 27.0
                uv = ((u0 / e_, -a[2] / e_), ((u0 + largo) / e_, -b[2] / e_), ((u0 + largo) / e_, -c[2] / e_),
                      (u0 / e_, -d[2] / e_))
                tex = ROCA if self.ruido.v(xm * 0.1, a[2] * 0.05, 7) > 0.35 else ROCA2
                self.q(ch, tex, b, a, d, c, (uv[1], uv[0], uv[3], uv[2]), n)
            self.muro_coll(ch, q_, p, 0.0, 2.6)        # barandilla invisible en el borde

    def en_camino(self, x, y):
        """Caminos de losas: de cada puerta al centro y del centro al puente."""
        for (ax, ay), (bx, by) in self.caminos:
            dx, dy = bx - ax, by - ay
            t = clamp(((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy), 0, 1)
            if math.hypot(x - (ax + dx * t), y - (ay + dy * t)) < 1.9:
                return True
        return False

    # ---- casas ----
    def casa(self, c):
        """Casa de piedra: muros gruesos con puerta y ventanas estrechas, tejado a dos aguas (hundido en
        las ruinas), chimenea alta. c: x0, x1, y0, y1, alto, puerta ('N','S','E','W'), ruina, chimenea."""
        x0, x1, y0, y1, h = c["x0"], c["x1"], c["y0"], c["y1"], c["alto"]
        g = 0.6
        ch = ("C", c["nombre"])
        L = self.luz
        cen = ((x0 + x1) / 2, (y0 + y1) / 2, 1.6)
        L.fuentes.append((cen, 4.5, 0.6))
        # suelo interior (también bajo el grosor del muro de la puerta)
        self.suelo(ch, LOSA_IRR, (x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0), esc=2.5,
                   interior=0.75)
        lados = {"S": ((x0, y0), (x1, y0)), "E": ((x1, y0), (x1, y1)), "N": ((x1, y1), (x0, y1)),
                 "W": ((x0, y1), (x0, y0))}
        for lado, (p0, p1) in lados.items():
            largo = math.dist(p0, p1)
            huecos = []
            if lado == c["puerta"]:
                huecos.append((largo / 2 - 1.25, largo / 2 + 1.25, 0.0, 3.1))    # 2,5 m: el jugador pasa holgado
            for v_ in c.get("ventanas", []):
                lv, s_ = v_[0], v_[1]
                za_ = v_[2] if len(v_) > 2 else 1.5
                if lv == lado:
                    huecos.append((s_ * largo - 0.3, s_ * largo + 0.3, za_, za_ + 1.4))
            altura = h if not c.get("ruina") else h * (0.55 if lado in ("E", "N") else 1.0)
            self.muro_huecos(ch, p0, p1, 0.0, altura, g, huecos, ruina=c.get("ruina", False))
        # hastiales y tejado (eje del tejado a lo largo del lado largo)
        largo_x = (x1 - x0) >= (y1 - y0)
        cumbre = h + c.get("cumbre", 2.6)
        if not c.get("ruina"):
            self.tejado(ch, x0, x1, y0, y1, h, cumbre, largo_x, hundido=c.get("hundido", False))
        if c.get("chimenea"):
            cx, cy = c["chimenea"]
            self.chimenea(ch, cx, cy, h + c.get("chimenea_alto", 5.5))
        self.casas.append(c)

    def muro_huecos(self, ch, p0, p1, z0, z1, g, huecos, ruina=False):
        """Muro de grosor g de p0 a p1 (la cara de fuera mira a la izquierda de p0->p1... hacia fuera de la
        casa, porque los lados van en sentido antihorario), con huecos (s0, s1, za, zb) en metros."""
        d = norm((p1[0] - p0[0], p1[1] - p0[1], 0.0))
        nout = (d[1], -d[0], 0.0)              # hacia fuera
        largo = math.dist(p0, p1)
        P = lambda s, off: (p0[0] + d[0] * s + nout[0] * off, p0[1] + d[1] * s + nout[1] * off)
        # en las esquinas: la tapa y la cara de dentro de este muro acaban a g del final (esa esquina
        # la cubre el muro siguiente), así no hay dos caras en el mismo plano
        cortes = sorted({0.0, g, largo - g, largo} | {h[0] for h in huecos} | {h[1] for h in huecos})
        for s_a, s_b in zip(cortes, cortes[1:]):
            sm = (s_a + s_b) / 2
            hz = [(h[2], h[3]) for h in huecos if h[0] - 1e-6 <= sm <= h[1] + 1e-6]
            tramos = [(z0, z1)]
            for (za, zb) in hz:
                nuevo = []
                for (ta, tb) in tramos:
                    if zb <= ta or za >= tb:
                        nuevo.append((ta, tb))
                        continue
                    if za > ta:
                        nuevo.append((ta, za))
                    if zb < tb:
                        nuevo.append((zb, tb))
                tramos = nuevo
            # el grosor del muro va hacia dentro: la cara de fuera está en el borde de la planta
            for (ta, tb) in tramos:
                tb_r = tb
                if ruina and tb == z1:
                    tb_r = tb - 1.2 * self.ruido.v(sm * 0.9, p0[0] * 0.3 + p0[1] * 0.3, 41)
                fa, fb = P(s_a, 0.0), P(s_b, 0.0)
                ia, ib = P(s_a, -g), P(s_b, -g)
                dentro_ok = s_a >= g - 1e-6 and s_b <= largo - g + 1e-6
                tapa_ok = s_b <= largo - g + 1e-6
                self.pared(ch, MURO, fb, fa, ta, tb_r, esc=3.0, ao_pie=(ta == z0), u0=-s_b)   # fuera
                if dentro_ok:
                    self.pared(ch, PIEDRA_LISA, ia, ib, ta, tb_r, esc=3.0, interior=0.7, ao_pie=(ta == z0), u0=s_a)
                if ta == z0:
                    self.muro_coll(ch, fb, fa, z0 - 0.5, 2.5)
                    if dentro_ok:
                        self.muro_coll(ch, ia, ib, z0 - 0.5, 2.5)
                if not tapa_ok:
                    continue
                # tapa de arriba / dintel de abajo
                top = ((fa[0], fa[1], tb_r), (fb[0], fb[1], tb_r), (ib[0], ib[1], tb_r), (ia[0], ia[1], tb_r))
                self.q(ch, MURO, top[1], top[0], top[3], top[2],
                       ((0, 0), (1, 0), (1, 0.25), (0, 0.25)), (0, 0, 1))
                if ta > z0:
                    bot = ((fa[0], fa[1], ta), (fb[0], fb[1], ta), (ib[0], ib[1], ta), (ia[0], ia[1], ta))
                    self.q(ch, MURO, *bot, ((0, 0), (1, 0), (1, 0.25), (0, 0.25)), (0, 0, -1), k=0.55)
        for (s0, s1, za, zb) in huecos:
            for s_, sg in ((s0, 1.0), (s1, -1.0)):
                fo, io = P(s_, 0.0), P(s_, -g)
                a, b = (fo[0], fo[1], za), (io[0], io[1], za)
                c, dd = (io[0], io[1], zb), (fo[0], fo[1], zb)
                n = (d[0] * sg, d[1] * sg, 0.0)
                self.q(ch, MURO, a, b, c, dd, ((0, -za / 3), (0.2, -za / 3), (0.2, -zb / 3), (0, -zb / 3)), n, k=0.8)
                if za <= z0 + 1e-6:
                    self.geo.cquad(ch, "wall", (fo[0], fo[1], z0 - 0.5), (io[0], io[1], z0 - 0.5),
                                   (io[0], io[1], z0 + 2.5), (fo[0], fo[1], z0 + 2.5))

    def tejado(self, ch, x0, x1, y0, y1, h, cumbre, largo_x, hundido=False):
        vuelo = 0.45
        if largo_x:
            ym = (y0 + y1) / 2
            caras = [((x0 - vuelo, y0 - vuelo, h - 0.3), (x1 + vuelo, y0 - vuelo, h - 0.3), (x1 + vuelo, ym, cumbre),
                      (x0 - vuelo, ym, cumbre)),
                     ((x1 + vuelo, y1 + vuelo, h - 0.3), (x0 - vuelo, y1 + vuelo, h - 0.3), (x0 - vuelo, ym, cumbre),
                      (x1 + vuelo, ym, cumbre))]
            hastiales = [((x0, y0), (x0, y1)), ((x1, y1), (x1, y0))]
        else:
            xm = (x0 + x1) / 2
            caras = [((x1 + vuelo, y0 - vuelo, h - 0.3), (x1 + vuelo, y1 + vuelo, h - 0.3), (xm, y1 + vuelo, cumbre),
                      (xm, y0 - vuelo, cumbre)),
                     ((x0 - vuelo, y1 + vuelo, h - 0.3), (x0 - vuelo, y0 - vuelo, h - 0.3), (xm, y0 - vuelo, cumbre),
                      (xm, y1 + vuelo, cumbre))]
            hastiales = [((x1, y0), (x0, y0)), ((x0, y1), (x1, y1))]
        for k_, (a, b, c, d) in enumerate(caras):
            if hundido and k_ == 1:
                # medio tejado caído: solo queda la franja del alero
                c = tuple(b[i] + (c[i] - b[i]) * 0.35 for i in range(3))
                d = tuple(a[i] + (d[i] - a[i]) * 0.35 for i in range(3))
            n = norm(cross(sub(b, a), sub(d, a)))
            self.q(ch, LOSA_IRR, a, b, c, d, ((0, 0), (math.dist(a, b) / 2.5, 0),
                                               (math.dist(a, b) / 2.5, math.dist(a, d) / 2.5),
                                               (0, math.dist(a, d) / 2.5)), n, k=0.95)
        # hastiales: triángulo sobre los muros cortos (quad con dos vértices en la cumbre)
        for (p0, p1) in hastiales:
            pm = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            a, b = (p0[0], p0[1], h), (p1[0], p1[1], h)
            c = (pm[0] + (p1[0] - pm[0]) * 0.02, pm[1] + (p1[1] - pm[1]) * 0.02, cumbre - 0.15)
            d = (pm[0] - (p1[0] - pm[0]) * 0.02, pm[1] - (p1[1] - pm[1]) * 0.02, cumbre - 0.15)
            n = norm((-(p1[1] - p0[1]), p1[0] - p0[0], 0.0))
            n = (-n[0], -n[1], 0.0) if dot(n, (pm[0] - (x0 + x1) / 2, pm[1] - (y0 + y1) / 2, 0)) < 0 else n
            self.q(ch, MURO, a, b, c, d, ((0, -h / 3), (math.dist(p0, p1) / 3, -h / 3),
                                          (math.dist(p0, p1) / 6, -cumbre / 3), (math.dist(p0, p1) / 6, -cumbre / 3)), n)

    def chimenea(self, ch, cx, cy, top):
        a = 0.7
        pts = [(cx - a, cy - a), (cx + a, cy - a), (cx + a, cy + a), (cx - a, cy + a)]
        for i in range(4):
            self.pared(ch, LADR, pts[(i + 1) % 4], pts[i], 0.0, top, esc=2.0)
            self.muro_coll(ch, pts[(i + 1) % 4], pts[i], -0.5, 2.5)
        self.q(ch, LADR, (pts[0][0], pts[0][1], top), (pts[1][0], pts[1][1], top), (pts[2][0], pts[2][1], top),
               (pts[3][0], pts[3][1], top), ((0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)), (0, 0, 1), k=0.5)

    # ---- muretes y ruinas ----
    def murete(self, p0, p1, alto=0.9, g=0.5):
        ch = ("R", int((p0[0] + p1[0]) / 40), int((p0[1] + p1[1]) / 40))
        d = norm((p1[0] - p0[0], p1[1] - p0[1], 0.0))
        nl = (-d[1] * g / 2, d[0] * g / 2)
        a0, a1 = (p0[0] + nl[0], p0[1] + nl[1]), (p1[0] + nl[0], p1[1] + nl[1])
        b0, b1 = (p0[0] - nl[0], p0[1] - nl[1]), (p1[0] - nl[0], p1[1] - nl[1])
        largo = math.dist(p0, p1)
        tops = [alto * (0.65 + 0.35 * self.ruido.v(p0[0] + t, p0[1], 47)) for t in (0, 1)]
        for (q0, q1) in ((a1, a0), (b0, b1)):
            self.pared(ch, MURO, q0, q1, 0.0, min(tops), esc=2.5)
        self.q(ch, MURO, (a0[0], a0[1], min(tops)), (b0[0], b0[1], min(tops)), (b1[0], b1[1], min(tops)),
               (a1[0], a1[1], min(tops)), ((0, 0), (0.2, 0), (0.2, largo / 2.5), (0, largo / 2.5)), (0, 0, 1))
        for (q0, q1) in ((a0, b0), (b1, a1)):
            self.pared(ch, MURO, q0, q1, 0.0, min(tops), esc=2.5)
        self.muro_coll(ch, a1, a0, -0.5, 2.4)
        self.muro_coll(ch, b0, b1, -0.5, 2.4)

    def ruinas(self):
        r = self.rng
        # una fila de columnas rotas (lo que queda de un pórtico) cerca del borde este
        for i in range(6):
            cx, cy = 17.0 + i * 0.4, -6.0 + i * 3.4
            alto = r.choice([2.2, 3.5, 6.0, 9.5, 11.0, 4.0])
            self.prisma(("P", 0), ESTRIA, (cx, cy), 0.55, -0.2, alto, lados=8, esc=3.0, coll=2.6, roto=0.6)
        # dintel caído
        self.prisma(("P", 0), SILLAR, (13.5, 4.0), 0.45, 0.0, 0.9, lados=4, coll=0.0)
        # dos columnas altísimas con su arco, al lado del arranque del puente
        for cx in (-6.5, 6.5):
            self.prisma(("P", 1), ESTRIA, (cx, 26.0), 0.8, -0.2, 16.4, lados=8, esc=4.0, coll=2.6)
        ch = ("P", 1)
        self.q(ch, BANDA, (-7.4, 25.2, 16.0), (7.4, 25.2, 16.0), (7.4, 25.2, 17.6), (-7.4, 25.2, 17.6),
               ((0, 0), (3.7, 0), (3.7, 0.4), (0, 0.4)), (0, -1, 0))
        self.q(ch, BANDA, (7.4, 26.8, 16.0), (-7.4, 26.8, 16.0), (-7.4, 26.8, 17.6), (7.4, 26.8, 17.6),
               ((0, 0), (3.7, 0), (3.7, 0.4), (0, 0.4)), (0, 1, 0))
        self.q(ch, BANDA, (-7.4, 25.2, 16.0), (-7.4, 26.8, 16.0), (7.4, 26.8, 16.0), (7.4, 25.2, 16.0),
               ((0, 0), (0.4, 0), (0.4, 3.7), (0, 3.7)), (0, 0, -1), k=0.5)
        self.q(ch, BANDA, (-7.4, 25.2, 17.6), (7.4, 25.2, 17.6), (7.4, 26.8, 17.6), (-7.4, 26.8, 17.6),
               ((0, 0), (3.7, 0), (3.7, 0.4), (0, 0.4)), (0, 0, 1))
        for x_ in (-7.4, 7.4):
            n = (-1 if x_ < 0 else 1, 0, 0)
            ys = (25.2, 26.8) if x_ > 0 else (26.8, 25.2)
            self.q(ch, BANDA, (x_, ys[0], 16.0), (x_, ys[1], 16.0), (x_, ys[1], 17.6), (x_, ys[0], 17.6),
                   ((0, 0), (0.4, 0), (0.4, 0.4), (0, 0.4)), n)

    # ======================= puente =======================
    def z_puente(self, y):
        t = clamp((y - self.puente_y0) / (self.puente_y1 - self.puente_y0), 0, 1)
        return self.puente_z0 + (self.puente_z1 - self.puente_z0) * t

    def puente(self):
        w = self.puente_ancho / 2
        y0, y1 = self.puente_y0, self.puente_y1
        tramo = 2.5
        n = int(round((y1 - y0) / tramo))
        luz_arco = 12.5                 # distancia entre pilas
        for i in range(n):
            ya, yb = y0 + i * tramo, y0 + (i + 1) * tramo
            za, zb = self.z_puente(ya), self.z_puente(yb)
            ch = ("B", int(ya // 30))
            self.suelo(ch, LOSA_IRR, (-w, ya, za), (w, ya, za), (w, yb, zb), (-w, yb, zb), esc=2.5)
            # pretiles bajos a los dos lados
            for sx in (-1, 1):
                xo, xi = sx * (w + 0.06), sx * (w - 0.45)     # el pretil sobresale un poco de la enjuta
                hp = 0.75
                pa, pb = (xo, ya), (xo, yb)
                ia, ib = (xi, ya), (xi, yb)
                if sx < 0:
                    self.pared(ch, SILLAR, pb, pa, za, zb + hp, esc=3.0, u0=-yb)
                    self.pared(ch, SILLAR, ia, ib, za, zb + hp, esc=3.0, u0=ya)
                else:
                    self.pared(ch, SILLAR, pa, pb, za, zb + hp, esc=3.0, u0=ya)
                    self.pared(ch, SILLAR, ib, ia, za, zb + hp, esc=3.0, u0=-yb)
                self.q(ch, SILLAR, (xo, ya, za + hp), (xo, yb, zb + hp), (xi, yb, zb + hp), (xi, ya, za + hp),
                       ((0, ya / 3), (0, yb / 3), (0.15, yb / 3), (0.15, ya / 3)), (0, 0, 1))
                self.muro_coll(ch, (xo, ya) if sx > 0 else (xo, yb), (xo, yb) if sx > 0 else (xo, ya), za - 0.5, 2.8)
        # costados con los arcos y pilas que bajan a la niebla
        ys = [y0 + 6.0 + k * luz_arco for k in range(int((y1 - y0 - 6.0) / luz_arco) + 1)]
        ys = [y for y in ys if y < y1 - 3.0]
        fondo = -200.0
        for k_, yp in enumerate(ys):
            ch = ("B", int(yp // 30))
            zp = self.z_puente(yp)
            # pila: un poco más ancha que el tablero
            a = 1.4
            pts = [(-w - 0.4, yp - a), (w + 0.4, yp - a), (w + 0.4, yp + a), (-w - 0.4, yp + a)]
            for i in range(4):
                p0, p1 = pts[i], pts[(i + 1) % 4]
                # cuanto más hondo, más grande la textura (se pierde en la niebla): menos trozos
                for (za_, zb_, e_) in ((fondo, -60.0, 30.0), (-60.0, -20.0, 9.0), (-20.0, zp - 4.2, 4.0)):
                    self.pared(ch, SILLAR, p1, p0, za_, zb_, esc=e_, ao_pie=False)
            # tajamar: escalón de la pila bajo los arcos
            for sx in (-1, 1):
                x_ = sx * (w + 0.4)
                pts_l = ((x_, yp - a), (x_, yp + a)) if sx > 0 else ((x_, yp + a), (x_, yp - a))
                self.pared(ch, BANDA, pts_l[0], pts_l[1], zp - 4.2, zp - 3.6, esc=1.5, ao_pie=False)
        # arcos: entre cada par de pilas, intradós y enjutas a ambos lados
        apoyos = [y0] + ys + [y1]
        for ya, yb in zip(apoyos, apoyos[1:]):
            if yb - ya < 4.0:
                continue
            ch = ("B", int(((ya + yb) / 2) // 30))
            a0 = ya + (1.4 if ya != y0 else 0.0)
            a1 = yb - (1.4 if yb != y1 else 0.0)
            segs = 8
            zarr = lambda y: self.z_puente(y)
            curva = []
            for s_ in range(segs + 1):
                t = s_ / segs
                y = a0 + (a1 - a0) * t
                alto_arco = (a1 - a0) / 2 * 0.95
                zc = zarr(y) - 1.1 - (alto_arco - alto_arco * math.sin(math.pi * t)) - 0.0
                curva.append((y, zc))
            for (ya_, za_), (yb_, zb_) in zip(curva, curva[1:]):
                # intradós
                self.q(ch, SILLAR, (-w - 0.01, yb_, zb_), (w + 0.01, yb_, zb_), (w + 0.01, ya_, za_),
                       (-w - 0.01, ya_, za_), ((0, yb_ / 3), (1.3, yb_ / 3), (1.3, ya_ / 3), (0, ya_ / 3)),
                       (0, 0, -1), k=0.45)
                # enjutas (de la curva hasta el tablero)
                for sx in (-1, 1):
                    x_ = sx * w
                    top_a, top_b = self.z_puente(ya_), self.z_puente(yb_)
                    if sx > 0:
                        self.q(ch, SILLAR, (x_, ya_, za_), (x_, yb_, zb_), (x_, yb_, top_b), (x_, ya_, top_a),
                               ((ya_ / 3, -za_ / 3), (yb_ / 3, -zb_ / 3), (yb_ / 3, -top_b / 3), (ya_ / 3, -top_a / 3)),
                               (1, 0, 0))
                    else:
                        self.q(ch, SILLAR, (x_, yb_, zb_), (x_, ya_, za_), (x_, ya_, top_a), (x_, yb_, top_b),
                               ((-yb_ / 3, -zb_ / 3), (-ya_ / 3, -za_ / 3), (-ya_ / 3, -top_a / 3),
                                (-yb_ / 3, -top_b / 3)), (-1, 0, 0))

    # ======================= barbacana y torre =======================
    def pared_honda(self, ch, tex, p0, p1, z0, z1, esc=4.0, ao_pie=False):
        """Pared que baja hasta la niebla: abajo con la textura más grande."""
        if z0 < -12.0 < z1:
            self.pared(ch, tex, p0, p1, z0, -12.0, esc=esc * 3, ao_pie=False)
            z0 = -12.0
        self.pared(ch, tex, p0, p1, z0, z1, esc=esc, ao_pie=ao_pie)

    def barbacana(self):
        y0 = self.barb_y0
        y1 = y0 + self.barb_fondo
        z = self.puente_z1
        hx = 8.0
        alto = 17.0
        ch = ("Bb", 0)
        g = 1.2
        # suelo del zaguán
        self.suelo(ch, LOSA_IRR, (-hx + g, y0, z), (hx - g, y0, z), (hx - g, y1 - g, z), (-hx + g, y1 - g, z),
                   esc=2.5, interior=0.6)
        # fachada con el portón en arco (de escalones) y los costados
        w_p, h_p = 2.2, 6.0
        cortes = [-hx, -w_p, w_p, hx]
        for xa, xb in zip(cortes, cortes[1:]):
            zb_ = z + (h_p if abs(xa + xb) < 1e-6 else 0.0)
            # fuera
            if abs(xa + xb) < 1e-6:
                self.pared(ch, SILLAR, (xb, y0), (xa, y0), z + h_p, z + alto, esc=4.0, ao_pie=False)
            else:
                self.pared_honda(ch, SILLAR, (xb, y0), (xa, y0), -40.0, z + alto, esc=4.0)
                self.muro_coll(ch, (xb, y0), (xa, y0), z - 0.5, 3.0)
        # jambas y bóveda del portón
        for sx in (-1, 1):
            x_ = sx * w_p
            pa, pb = ((x_, y0), (x_, y0 + g)) if sx > 0 else ((x_, y0 + g), (x_, y0))
            self.pared(ch, SILLAR, pa, pb, z, z + h_p, esc=3.0, k=0.7)
            self.muro_coll(ch, pa, pb, z - 0.5, 3.0)
        self.q(ch, SILLAR, (-w_p, y0, z + h_p), (w_p, y0, z + h_p), (w_p, y0 + g, z + h_p), (-w_p, y0 + g, z + h_p),
               ((0, 0), (1.4, 0), (1.4, 0.3), (0, 0.3)), (0, 0, -1), k=0.4)
        # base maciza bajo el portón (de la niebla al tablero)
        self.pared_honda(ch, SILLAR, (w_p, y0), (-w_p, y0), -40.0, z, esc=4.0)
        # costados y techo del zaguán (por dentro, en penumbra)
        for (pa, pb) in (((-hx + g, y1 - g), (-hx + g, y0 + g)), ((hx - g, y0 + g), (hx - g, y1 - g))):
            self.pared(ch, PIEDRA_LISA, pa, pb, z, z + 9.0, esc=3.0, interior=0.8)
            self.muro_coll(ch, pa, pb, z - 0.5, 3.0)
        self.pared(ch, PIEDRA_LISA, (-hx + g, y0 + g), (-w_p, y0 + g), z, z + 9.0, esc=3.0, interior=0.8)
        self.pared(ch, PIEDRA_LISA, (w_p, y0 + g), (hx - g, y0 + g), z, z + 9.0, esc=3.0, interior=0.8)
        self.q(ch, PIEDRA_LISA, (-hx + g, y1 - g, z + 9.0), (hx - g, y1 - g, z + 9.0), (hx - g, y0 + g, z + 9.0),
               (-hx + g, y0 + g, z + 9.0), ((0, 0), (4, 0), (4, 3), (0, 3)), (0, 0, -1), interior=0.85)
        # fondo: el portón de la torre, cerrado (siguiente fase: el interior)
        self.pared(ch, PIEDRA_LISA, (hx - g, y1 - g), (2.0, y1 - g), z, z + 9.0, esc=3.0, interior=0.8)
        self.pared(ch, PIEDRA_LISA, (-2.0, y1 - g), (-hx + g, y1 - g), z, z + 9.0, esc=3.0, interior=0.8)
        self.pared(ch, PIEDRA_LISA, (2.0, y1 - g), (-2.0, y1 - g), z + 5.0, z + 9.0, esc=3.0, interior=0.8)
        self.pared(ch, MADERA, (2.0, y1 - g + 0.05), (-2.0, y1 - g + 0.05), z, z + 5.0, esc=2.0, interior=0.6)
        self.muro_coll(ch, (hx - g, y1 - g), (-hx + g, y1 - g), z - 0.5, 3.0)
        # laterales y coronación de la barbacana por fuera
        self.pared_honda(ch, SILLAR, (hx, y1), (hx, y0), -40.0, z + alto, esc=4.0)
        self.pared_honda(ch, SILLAR, (-hx, y0), (-hx, y1), -40.0, z + alto, esc=4.0)
        self.q(ch, BANDA, (-hx - 0.4, y0 - 0.4, z + alto), (hx + 0.4, y0 - 0.4, z + alto),
               (hx + 0.4, y0 - 0.4, z + alto + 1.2), (-hx - 0.4, y0 - 0.4, z + alto + 1.2),
               ((0, 0), (5, 0), (5, 0.4), (0, 0.4)), (0, -1, 0))
        self.q(ch, SILLAR, (-hx - 0.4, y0 - 0.4, z + alto + 1.2), (hx + 0.4, y0 - 0.4, z + alto + 1.2),
               (hx + 0.4, y1, z + alto + 1.2), (-hx - 0.4, y1, z + alto + 1.2), ((0, 0), (4, 0), (4, 3), (0, 3)),
               (0, 0, 1))
        # almenas
        for i in range(7):
            x_ = -hx + 0.6 + i * 2.5
            self.prisma(ch, SILLAR, (x_, y0 + 0.2), 0.55, z + alto + 1.2, z + alto + 2.6, lados=4)
        self.puertas.append({"x": 0.0, "y": y1 - g, "z": z})

    def torre(self):
        """La torre de Tower Dungeon: una base maciza de sillares y encima pisos y pisos de columnas
        altísimas y juntas, con el muro de detrás en negro, separados por cinturones gruesos de piedra."""
        cx, cy = self.torre_c
        R = self.torre_r
        segs = 60
        base_top = 24.0
        piso, cinturon = 30.0, 7.0                 # alto de las columnas y del cinturón de cada piso
        fondo_col = 7.0                            # el muro de detrás de las columnas, hundido
        rr = self.rng
        ang0 = -math.pi / 2                        # el segmento 0 mira al puente
        finos = [-260.0, -150.0, -80.0, -40.0, -18.0, -6.0, 0.0, 6.0, 12.0, 18.0, base_top]
        gruesos = [-260.0, -120.0, -40.0, -6.0, 12.0, base_top]
        pisos = []
        z = base_top
        while z < 430.0:
            pisos.append((z, z + piso, z + piso + cinturon))
            z += piso + cinturon
        P = lambda r_, a_: (cx + r_ * math.cos(a_), cy + r_ * math.sin(a_))
        for s_ in range(segs):
            a0 = ang0 + 2 * math.pi * s_ / segs
            a1 = ang0 + 2 * math.pi * (s_ + 1) / segs
            am = (a0 + a1) / 2
            junto = s_ in (0, 1, segs - 1, segs - 2)
            n_out = (math.cos(am), math.sin(am), 0.0)
            ancho = 2 * math.pi * R / segs
            u_a, u_b = s_ * ancho / 6.0, (s_ + 1) * ancho / 6.0
            # base
            cortes = finos if junto else gruesos
            for za, zb in zip(cortes, cortes[1:]):
                ch = ("T", s_ // 6, int((za + 260) // 240))
                p0, p1 = P(R, a0), P(R, a1)
                tex = NICHO if (za >= 0 and rr.random() < 0.15) else SILLAR
                e_ = 6.0 if za > -20 else 24.0
                self.q(ch, tex, (p1[0], p1[1], za), (p0[0], p0[1], za), (p0[0], p0[1], zb), (p1[0], p1[1], zb),
                       ((u_b * 6 / e_, -za / e_), (u_a * 6 / e_, -za / e_), (u_a * 6 / e_, -zb / e_),
                        (u_b * 6 / e_, -zb / e_)), n_out, cerca=junto)
            for k_, (z0, z1, z2) in enumerate(pisos):
                ch = ("T", s_ // 6, int((z0 + 260) // 240))
                # suelo del piso (de la base o del cinturón de abajo) y techo, entre el fondo y el borde
                ri, ro = R - fondo_col, R + 1.2
                for zz, nz, kk, tex in ((z0, 1.0, 1.0, BANDA), (z1, -1.0, 0.22, SILLAR)):
                    q_ = [(*P(ri, a0), zz), (*P(ri, a1), zz), (*P(ro, a1), zz), (*P(ro, a0), zz)]
                    if nz < 0:
                        q_ = q_[::-1]
                    self.q(ch, tex, *q_, ((0, 0), (2.0, 0), (2.0, 1.0), (0, 1.0)), (0, 0, nz), k=kk, cerca=False)
                # muro del fondo, en sombra casi negra (los huecos negros entre columnas)
                p0, p1 = P(ri, a0), P(ri, a1)
                self.q(ch, PIEDRA_LISA, (p1[0], p1[1], z0), (p0[0], p0[1], z0), (p0[0], p0[1], z1),
                       (p1[0], p1[1], z1), ((u_b, -z0 / 6), (u_a, -z0 / 6), (u_a, -z1 / 6), (u_b, -z1 / 6)),
                       n_out, k=0.12, cerca=False)
                # cinturón de sillares, algo saliente, con su canto
                p0, p1 = P(ro, a0), P(ro, a1)
                self.q(ch, SILLAR, (p1[0], p1[1], z1), (p0[0], p0[1], z1), (p0[0], p0[1], z2), (p1[0], p1[1], z2),
                       ((u_b, -z1 / 4), (u_a, -z1 / 4), (u_a, -z2 / 4), (u_b, -z2 / 4)), n_out, cerca=False)
                if k_ == 0:
                    pb0, pb1 = P(R, a0), P(R, a1)
                    # el escalón entre la base (R) y el borde del primer suelo (R + 1.2)
                    self.q(ch, BANDA, (pb1[0], pb1[1], z0 - 1.2), (pb0[0], pb0[1], z0 - 1.2),
                           (p0[0], p0[1], z0), (p1[0], p1[1], z0), ((u_b, 1), (u_a, 1), (u_a, 0), (u_b, 0)),
                           (n_out[0] * 0.7, n_out[1] * 0.7, -0.7), k=0.5, cerca=False)
                # columnas: dos por segmento, cuadradas y estriadas; muchas rotas en lo alto de algún piso
                for f_ in (0.25, 0.75):
                    a_ = a0 + (a1 - a0) * f_
                    pc = P(R - 1.6, a_)
                    self.columna_cuadrada(ch, pc, a_, 1.15, z0, z1 + 0.3)
        # piso más alto: se pierde en la niebla

    def columna_cuadrada(self, ch, c, ang, r, z0, z1):
        """Columna de planta cuadrada orientada a la torre: solo las tres caras que se ven desde fuera."""
        ca, sa = math.cos(ang), math.sin(ang)
        fuera = (ca, sa)
        lado = (-sa, ca)
        esquinas = [(c[0] + (fuera[0] * i + lado[0] * j) * r, c[1] + (fuera[1] * i + lado[1] * j) * r)
                    for i, j in ((1, -1), (1, 1), (-1, 1), (-1, -1))]
        caras = [(esquinas[0], esquinas[1], (ca, sa, 0.0)), (esquinas[1], esquinas[2], (lado[0], lado[1], 0.0)),
                 (esquinas[3], esquinas[0], (-lado[0], -lado[1], 0.0))]
        for (p0, p1, n) in caras:
            self.q(ch, ESTRIA, (p0[0], p0[1], z0), (p1[0], p1[1], z0), (p1[0], p1[1], z1), (p0[0], p0[1], z1),
                   ((0, -z0 / 8), (1, -z0 / 8), (1, -z1 / 8), (0, -z1 / 8)), n, ao=(0.5, 0.5, 1, 1), cerca=False)

    # ---- ruinas gigantes de columnas sobre peñascos (la primera imagen) ----
    def peñasco(self, c, r, top):
        ch = ("K", round(c[0]), round(c[1]))
        lados = 10
        niveles = [top, top - 3.0, top - 10.0, top - 30.0, top - 70.0, -150.0]
        anillos = []
        for z in niveles:
            fila = []
            for i in range(lados):
                ang = 2 * math.pi * i / lados
                rr_ = r * (0.85 + 0.3 * self.ruido.v(ang * 2 + c[0], z * 0.05, 101)) * (1.0 + max(0.0, top - z) * 0.004)
                fila.append((c[0] + rr_ * math.cos(ang), c[1] + rr_ * math.sin(ang), z))
            anillos.append(fila)
        for fa, fb in zip(anillos, anillos[1:]):
            for i in range(lados):
                a, b = fa[i], fa[(i + 1) % lados]
                cc, d = fb[(i + 1) % lados], fb[i]
                ang = 2 * math.pi * (i + 0.5) / lados
                n = (math.cos(ang), math.sin(ang), 0.0)
                e_ = 6.0 if d[2] > top - 12 else 30.0
                self.q(ch, ROCA, d, cc, b, a, ((i * 1.0, -d[2] / e_), ((i + 1) * 1.0, -cc[2] / e_),
                                               ((i + 1) * 1.0, -b[2] / e_), (i * 1.0, -a[2] / e_)), n, cerca=False)
        cen = (c[0], c[1], top)
        f = anillos[0]
        for i in range(0, lados, 2):
            self.q(ch, ROCA_MUSGO, cen, f[i], f[(i + 1) % lados], f[(i + 2) % lados],
                   ((0, 0), (1, 0), (1, 1), (0, 1)), (0, 0, 1), cerca=False)
        return ch

    def ruina_columnas(self, c, lado_m, top, pisos=3):
        """Un pórtico cuadrado en ruinas, de pisos de columnas altas: lo que queda de otra torre."""
        ch = self.peñasco(c, lado_m * 0.75, top)
        rr = self.rng
        h_piso = 16.0
        cols = 6
        z = top
        for k_ in range(pisos):
            for lado in range(4):
                ang = math.pi / 2 * lado
                d = (math.cos(ang), math.sin(ang))
                t = (-d[1], d[0])
                for i in range(cols):
                    if rr.random() < 0.18 * k_:
                        continue                   # columnas caídas en los pisos altos
                    f = (i + 0.5) / cols - 0.5
                    pc = (c[0] + d[0] * lado_m / 2 + t[0] * f * lado_m, c[1] + d[1] * lado_m / 2 + t[1] * f * lado_m)
                    alto = h_piso if (k_ < pisos - 1 or rr.random() < 0.4) else h_piso * rr.uniform(0.3, 0.9)
                    self.prisma(ch, ESTRIA, pc, 0.75, z, z + alto, lados=4, esc=6.0, roto=0.0 if alto == h_piso else 0.8,
                                tapa=alto != h_piso, cerca=False)
                # cinturón sobre las columnas (roto en el piso de arriba)
                if k_ < pisos - 1:
                    p0 = (c[0] + d[0] * (lado_m / 2 + 1) - t[0] * (lado_m / 2 + 1),
                          c[1] + d[1] * (lado_m / 2 + 1) - t[1] * (lado_m / 2 + 1))
                    p1 = (c[0] + d[0] * (lado_m / 2 + 1) + t[0] * (lado_m / 2 + 1),
                          c[1] + d[1] * (lado_m / 2 + 1) + t[1] * (lado_m / 2 + 1))
                    self.q(ch, SILLAR, (p0[0], p0[1], z + h_piso), (p1[0], p1[1], z + h_piso),
                           (p1[0], p1[1], z + h_piso + 3.0), (p0[0], p0[1], z + h_piso + 3.0),
                           ((0, 0), (lado_m / 4, 0), (lado_m / 4, 0.75), (0, 0.75)), (d[0], d[1], 0.0), cerca=False)
            # muro del fondo, negro, dentro del pórtico
            m = lado_m / 2 - 2.5
            esq = [(c[0] - m, c[1] - m), (c[0] + m, c[1] - m), (c[0] + m, c[1] + m), (c[0] - m, c[1] + m)]
            for i in range(4):
                p0, p1 = esq[i], esq[(i + 1) % 4]
                n = norm(((p0[0] + p1[0]) / 2 - c[0], (p0[1] + p1[1]) / 2 - c[1], 0.0))
                self.q(ch, PIEDRA_LISA, (p1[0], p1[1], z), (p0[0], p0[1], z), (p0[0], p0[1], z + h_piso),
                       (p1[0], p1[1], z + h_piso), ((0, 0), (2, 0), (2, 2), (0, 2)), n, k=0.12, cerca=False)
            z += h_piso + 3.0

    def llanura(self):
        """La llanura rocosa de abajo, que se pierde en la niebla."""
        paso = 160.0
        zb = -150.0
        for i in range(-4, 4):
            for j in range(-3, 5):
                x0, y0 = i * paso, j * paso
                ch = ("L", i // 2, j // 2)
                pts = []
                for (x, y) in ((x0, y0), (x0 + paso, y0), (x0 + paso, y0 + paso), (x0, y0 + paso)):
                    h = zb + 25.0 * self.ruido.fbm(x * 0.004, y * 0.004, 111, 3)
                    pts.append((x, y, h))
                self.q(ch, ROCA_MUSGO, *pts, tuple((p[0] / 40.0, p[1] / 40.0) for p in pts), (0, 0, 1), cerca=False)

    # ======================= montaje =======================
    def construir(self):
        # casas: la primera es la de inicio (puerta al norte, mirando a la torre)
        self.casas_def = [
            # casas altas y estrechas, de dos plantas, tejado muy empinado y chimenea altísima (el dibujo)
            {"nombre": "inicio", "x0": -17.5, "x1": -12.5, "y0": -15.0, "y1": -7.5, "alto": 8.0, "puerta": "N",
             "cumbre": 4.8, "chimenea": (-15.0, -15.8), "chimenea_alto": 7.5,
             "ventanas": [("W", 0.5), ("E", 0.35, 4.6), ("E", 0.7, 4.6), ("W", 0.25, 4.6), ("N", 0.5, 4.9)]},
            {"nombre": "este", "x0": 5.0, "x1": 10.0, "y0": -12.5, "y1": -5.0, "alto": 7.0, "puerta": "W",
             "cumbre": 4.2, "chimenea": (10.8, -11.0), "chimenea_alto": 6.0, "hundido": True,
             "ventanas": [("N", 0.5, 4.2), ("S", 0.5), ("E", 0.3, 4.0), ("E", 0.7, 4.0)]},
            {"nombre": "ruina", "x0": -15.0, "x1": -7.5, "y0": 5.0, "y1": 12.5, "alto": 6.0, "puerta": "E",
             "ventanas": [("S", 0.5), ("S", 0.5, 3.8), ("W", 0.5, 3.8)], "ruina": True},
        ]
        self.caminos = [((-15.0, -7.0), (-4.0, 2.0)), ((5.0, -8.75), (-1.0, 2.0)), ((-7.0, 8.75), (-3.0, 4.0)),
                        ((-2.0, 2.0), (0.0, 31.0))]
        for c in self.casas_def:
            self.casa(c)
        self.risco()
        self.murete((-24.0, 0.0), (-18.0, 3.0))
        self.murete((-3.5, 14.0), (-3.0, 22.0))
        self.murete((3.5, 18.0), (3.0, 24.0), alto=0.7)
        self.murete((14.0, -16.0), (19.0, -12.0))
        self.ruinas()
        self.puente()
        self.barbacana()
        self.torre()
        self.ruina_columnas((-62.0, 45.0), 22.0, 6.0, pisos=3)
        self.ruina_columnas((70.0, 70.0), 18.0, -4.0, pisos=4)
        self.ruina_columnas((-48.0, 115.0), 14.0, -12.0, pisos=2)
        self.llanura()
        # intro: dentro de la casa de inicio, mirando a la puerta (y a la torre)
        x_ = -15.0
        self.intro = [(x_, -13.2, 0.0), (x_, -11.4, 0.0), (x_, -10.9, 0.0)]
        self.inicio = self.intro[-1]
        # objetos
        self.objetos = [(6, (-16.3, -9.0, 0.0)), (6, (-13.6, -13.6, 0.0)),            # 2 hierbas en casa
                        (151, (8.6, -10.5, 0.0)), (7, (6.2, -6.5, 0.0)),              # cachiporra, jugo
                        (251, (-12.5, 9.0, 0.0)), (6, (-10.0, 7.0, 0.0))]             # casco en la ruina
        self.guardado = (-16.4, -12.6, 0.0)
        # pocos enemigos: dos plantas en las ruinas y un escarabajo al final del puente
        self.enemigos = [("planta", (18.5, 2.0, 0.0)), ("planta", (-21.0, 6.0, 0.0)),
                         ("escarabajo", (1.0, 150.0, self.z_puente(150.0)))]
        self.spawns_pos = [p for _, p in self.enemigos]
