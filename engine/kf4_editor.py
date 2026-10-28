#!/usr/bin/env python3
"""
kf4_editor.py - Convierte un mapa hecho en el Editor de La Torre (archivo .json) en geometría de KF4.

El editor guarda:
  - una rejilla de terreno: alturas en cada esquina y una textura por celda (0 = hueco, vacío);
  - piezas colocadas: casa, columna, murete, puente, barbacana, torre, ruina, escaleras, portal;
  - el inicio del jugador, el punto de guardado, objetos del suelo y enemigos;
  - el color y la distancia de la niebla.

kf4_valle.py lo usa con --zona editor --mapa mapa_torre.json. Las piezas se construyen con las mismas
funciones del prólogo (kf4_prologo.py) y se colocan con su posición y giro.
"""

import json
import math

import kf4_valle as kv
import kf4_prologo as kp
from kf4_valle import Geo, Ruido, norm, cross, sub, clamp

# nombre en el editor -> textura (TBP, CBP) de 099
TEXTURAS = {
    "losas": kp.LOSA_IRR, "sillar": kp.SILLAR, "muro": kp.MURO, "roca": kp.ROCA, "roca_gris": kp.ROCA2,
    "musgo": kp.ROCA_MUSGO, "grava": kp.GRAVA, "piedra_lisa": kp.PIEDRA_LISA, "ladrillo": kp.LADR,
    "banda": kp.BANDA, "estrias": kp.ESTRIA, "madera": kp.MADERA, "friso": kp.FRISO, "nicho": kp.NICHO,
}
PENDIENTE_MURO = 1.0     # por encima de 1 m de subida por metro, la celda es pared en la colisión
ESCALON = 0.35           # un desnivel mayor entre casillas vecinas es pared en la colisión


PEZ_HONDO = 2.6        # m bajo la superficie: más que su radio de vuelta (kf4_valle._spawn_pez), así no asoman

class Constructor(kp.Prologo):
    """Un prólogo vacío: solo se usan sus funciones de construcción, cada pieza en su propio Geo."""

    def __init__(self, semilla):
        super().__init__(semilla)
        self.luz = kp.LuzDia(self.ruido)        # su propia luz (las de las casas son locales a la pieza)
        self.geo = Geo()


def girar(p, ang):
    c, s = math.cos(ang), math.sin(ang)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


class MapaEditor(kp.Prologo):
    def __init__(self, semilla, ruta):
        super().__init__(semilla)
        if isinstance(ruta, dict):            # el editor local manda el mapa ya leído
            self.mapa = ruta
        else:
            with open(ruta, encoding="utf-8") as f:
                self.mapa = json.load(f)
        m = self.mapa
        self.niebla = tuple(int(v) for v in m.get("niebla", list(self.niebla)))
        self.niebla_k = float(m.get("niebla_k", self.niebla_k))
        self.rumbo = math.radians(float(m.get("inicio", {}).get("rumbo", 0.0)))

    # ---- terreno y casillas ----
    # Cada celda de la rejilla es una de estas:
    #   terreno: sus cuatro esquinas son las alturas compartidas del terreno (lo que se esculpe);
    #   suelo:   una casilla construida, plana a la altura f (un muro es una casilla alta);
    #   escalera: sube de f0 a f1 en una dirección, con peldaños;
    #   vacío:   no hay nada (abismo).
    # Entre dos celdas vecinas se comparan sus perfiles a lo largo de la arista común y se levanta la
    # cara que falta, del lado que queda a la vista. Las caras comparten exactamente los puntos de la
    # arista: no quedan rendijas. Contra el vacío, la cara baja `borde_prof` metros y se funde con la niebla.
    def _h(self, i, j):
        n = self.n
        i = min(max(i, 0), n)
        j = min(max(j, 0), n)
        return float(self.alturas[j * (n + 1) + i])

    def tex_celda(self, i, j):
        if not (0 <= i < self.n and 0 <= j < self.n):
            return 0
        return int(self.texturas[j * self.n + i])

    def _tex(self, nombre, defecto):
        return TEXTURAS.get(nombre, TEXTURAS.get(defecto, kp.LOSA_IRR))

    def celda_en(self, i, j):
        """None = vacío; 'tapada' = la cubre una pieza (casa, puente); si no, un dict con la celda."""
        if not (0 <= i < self.n and 0 <= j < self.n):
            return None
        if (i, j) in self.tapadas:
            return "tapada"
        k = (i, j)
        if k in self.cache:
            return self.cache[k]
        c = self.construidas.get(k)
        pal = self.paleta
        out = None
        if c is not None:
            if c.get("vacio"):
                out = None
            else:
                tex = c.get("tex", "losas")
                out = {"tipo": "suelo", "tex": tex, "pared": c.get("pared", tex),
                       "techo": c.get("techo"), "ttex": c.get("ttex", c.get("pared", tex)),
                       "i": i, "j": j, "cc": c.get("cc")}
                if c.get("tapa") is False:      # bloque sin cara de arriba (roca que llega al techo)
                    out["tapa"] = False
                esc = c.get("esc")
                if esc:
                    d, f0, f1 = esc[0], float(esc[1]), float(esc[2])
                    out.update(tipo="escalera", dir=d, f0=f0, f1=f1)
                    lo = {"N": "S", "S": "N", "E": "W", "W": "E"}[d]
                    # esquinas (00, 10, 11, 01) de la rampa: el lado bajo a f0, el alto a f1
                    if d == "N":
                        out["esq"] = (f0, f0, f1, f1)
                    elif d == "S":
                        out["esq"] = (f1, f1, f0, f0)
                    elif d == "E":
                        out["esq"] = (f0, f1, f1, f0)
                    else:
                        out["esq"] = (f1, f0, f0, f1)
                    out["bajo"] = lo
                else:
                    f = float(c.get("f", 0.0))
                    out["esq"] = (f, f, f, f)
        else:
            t = self.tex_celda(i, j)
            if t:
                nombre = pal[t] if t < len(pal) else "losas"
                pt = self.paredes[j * self.n + i] if self.paredes else 0
                pared = pal[pt] if pt and pt < len(pal) else self.pared_terreno
                tc = self.techos_terreno.get(k)
                out = {"tipo": "terreno", "tex": nombre, "pared": pared, "techo": tc.get("techo") if tc else None,
                       "ttex": tc.get("ttex", "muro") if tc else "muro",
                       "esq": (self._h(i, j), self._h(i + 1, j), self._h(i + 1, j + 1), self._h(i, j + 1)),
                       "i": i, "j": j, "cc": None}
        # un techo que no queda por encima del suelo (p. ej. sobre un muro igual de alto) no existe
        if out is not None and out.get("techo") is not None and float(out["techo"]) <= max(out["esq"]) + 0.05:
            out["techo"] = None
        if out is not None and out.get("techo") is not None:
            out["techo"] = float(out["techo"])
        self.cache[k] = out
        return out

    @staticmethod
    def _pasos(c):
        return max(1, int(math.floor(abs(c["f1"] - c["f0"]) / 0.3 + 0.5)))     # como Math.round del editor

    def perfil(self, c, lado):
        """Perfil de la celda en una arista: lista de tramos (t0, t1, h0, h1), con t a lo largo de +x
        (aristas S y N) o de +y (aristas W y E)."""
        h00, h10, h11, h01 = c["esq"]
        if c["tipo"] != "escalera":
            return [(0.0, 1.0, *{"S": (h00, h10), "N": (h01, h11), "W": (h00, h01), "E": (h10, h11)}[lado])]
        d, f0, f1 = c["dir"], c["f0"], c["f1"]
        eje = "y" if d in "NS" else "x"
        lado_eje = "y" if lado in "WE" else "x"      # las aristas W/E corren a lo largo de y
        if lado_eje != eje:                          # arista de arranque o de llegada: plana
            alto = {"N": "N", "S": "S", "E": "E", "W": "W"}[d] == lado
            h = f1 if alto else f0
            return [(0.0, 1.0, h, h)]
        n = self._pasos(c)
        dz = (f1 - f0) / n
        out = []
        for m in range(n):
            k = m if d in "NE" else n - 1 - m
            h = f0 + (k + 1) * dz
            out.append((m / n, (m + 1) / n, h, h))
        return out

    def altura(self, x, y):
        """Altura del suelo en (x, y): la de la casilla construida o la del terreno, interpolada."""
        fx = (x - self.ox) / self.celda
        fy = (y - self.oy) / self.celda
        i, j = int(math.floor(fx)), int(math.floor(fy))
        tx, ty = fx - i, fy - j
        c = self.celda_en(i, j) if hasattr(self, "cache") else None
        if isinstance(c, dict):
            h00, h10, h11, h01 = c["esq"]
        else:
            h00, h10 = self._h(i, j), self._h(i + 1, j)
            h01, h11 = self._h(i, j + 1), self._h(i + 1, j + 1)
        return (h00 * (1 - tx) + h10 * tx) * (1 - ty) + (h01 * (1 - tx) + h11 * tx) * ty

    def color_en(self, x, y):
        """Color pintado (multiplicador, 1.0 = sin cambio) en (x, y)."""
        if not self.colores:
            return (1.0, 1.0, 1.0)
        n = self.n
        fx = clamp((x - self.ox) / self.celda, 0, n)
        fy = clamp((y - self.oy) / self.celda, 0, n)
        i, j = min(int(fx), n - 1), min(int(fy), n - 1)
        tx, ty = fx - i, fy - j

        def c(ii, jj):
            v = int(self.colores[jj * (n + 1) + ii])
            return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
        a, b, d, e = c(i, j), c(i + 1, j), c(i, j + 1), c(i + 1, j + 1)
        return tuple(((a[k] * (1 - tx) + b[k] * tx) * (1 - ty) + (d[k] * (1 - tx) + e[k] * tx) * ty) / 128.0
                     for k in range(3))

    def color_celda(self, A, p):
        """Color pintado de un vértice: el terreno usa la rejilla de colores (compartida); una casilla construida,
        los colores de sus cuatro esquinas (así se tiñe la esquina de un bloque sin tocar el suelo de abajo)."""
        if not isinstance(A, dict) or A["tipo"] == "terreno":
            return self.color_en(p[0], p[1])
        if not A.get("cc"):
            return (1.0, 1.0, 1.0)
        C = self.celda
        tx = clamp((p[0] - (self.ox + A["i"] * C)) / C, 0, 1)
        ty = clamp((p[1] - (self.oy + A["j"] * C)) / C, 0, 1)
        g = [((int(v) >> 16) & 255, (int(v) >> 8) & 255, int(v) & 255) for v in A["cc"]]   # 00, 10, 11, 01
        a, b, c, d = g
        return tuple(((a[k] * (1 - tx) + b[k] * tx) * (1 - ty) + (d[k] * (1 - tx) + c[k] * tx) * ty) / 128.0
                     for k in range(3))

    def luzv(self, p, n, interior=0.0, fondo=0.0, celda=False):
        """Luz horneada x color pintado; `fondo` (0..1) funde el vértice con la niebla. celda: de quién toma el
        color pintado (False: de la rejilla del terreno)."""
        col = self.luz.piedra(p, n, 1.0, interior)
        m = self.color_en(p[0], p[1]) if celda is False else self.color_celda(celda, p)
        col = tuple(clamp(col[k] * m[k], 0, 255) for k in range(3))
        if fondo > 0:
            nb = self.niebla
            col = tuple(col[k] * (1 - fondo) + nb[k] * 0.62 * fondo for k in range(3))
        return col

    def _esc_tex(self, tex):
        if getattr(self, "escala_tex", None):          # mapas de King's Field II: una textura por casilla
            return self.escala_tex
        return 3.0 if tex == kp.LOSA_IRR else 4.0

    def _cara(self, ch, tex, p0, p1, lo0, lo1, up0, up1, nrm, esc, interior=0.0, fondo=False, coll=False,
              clo=False, cup=False):
        """Cara vertical sobre la arista p0-p1, de las alturas lo a las up (las dos pueden ir inclinadas)."""
        if max(up0 - lo0, up1 - lo1) < 0.005:
            return
        a, b = (p0[0], p0[1], lo0), (p1[0], p1[1], lo1)
        c, d = (p1[0], p1[1], up1), (p0[0], p0[1], up0)
        u0 = (p0[0] + p0[1]) / esc
        u1 = (p1[0] + p1[1]) / esc
        uv = ((u0, -lo0 / esc), (u1, -lo1 / esc), (u1, -up1 / esc), (u0, -up0 / esc))
        prof = max(0.01, self.borde_prof)
        f = (lambda z, top: clamp((top - z) / prof, 0, 1) ** 1.3) if fondo else (lambda z, top: 0.0)
        cols = [self.luzv(a, nrm, interior, f(lo0, up0), clo), self.luzv(b, nrm, interior, f(lo1, up1), clo),
                self.luzv(c, nrm, interior, 0.0, cup), self.luzv(d, nrm, interior, 0.0, cup)]
        self.geo.quad(ch, tex, a, b, c, d, *uv, *cols, nrm, cerca=True)
        if coll:
            self.geo.cquad(ch, "wall", a, b, c, d)

    def _caras_arista(self, ch, A, B, lado_A, pA, pB, nrm_hacia_B, contra_vacio):
        """Caras entre la celda A y su vecina B (o el vacío) en la arista común."""
        perfA = self.perfil(A, lado_A)
        opuesto = {"S": "N", "N": "S", "W": "E", "E": "W"}[lado_A]
        perfB = None if contra_vacio else self.perfil(B, opuesto)
        cortes = sorted({0.0, 1.0} | {t for tr in perfA for t in tr[:2]} | ({t for tr in perfB for t in tr[:2]} if perfB else set()))

        def val(perf, t, lado_izq):
            for (t0, t1, h0, h1) in perf:
                if (t0 <= t < t1) if lado_izq else (t0 < t <= t1):
                    return h0 + (h1 - h0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0)
            return perf[-1][3] if not lado_izq else perf[0][2]
        P = lambda t: (pA[0] + (pB[0] - pA[0]) * t, pA[1] + (pB[1] - pA[1]) * t)
        intA = 0.55 if A.get("techo") is not None else 0.0
        for t0, t1 in zip(cortes, cortes[1:]):
            if t1 - t0 < 1e-6:
                continue
            a0, a1 = val(perfA, t0, True), val(perfA, t1, False)
            if contra_vacio:
                tex = self._tex(A["pared"], "roca")
                self._cara(ch, tex, P(t0), P(t1), a0 - self.borde_prof, a1 - self.borde_prof, a0, a1,
                           nrm_hacia_B, self._esc_tex(tex), fondo=True, clo=A, cup=A)
                if self.barandilla:
                    q0, q1 = P(t0), P(t1)
                    self.geo.cquad(ch, "wall", (q0[0], q0[1], a0 - 0.5), (q1[0], q1[1], a1 - 0.5),
                                   (q1[0], q1[1], a1 + 2.6), (q0[0], q0[1], a0 + 2.6))
                continue
            b0, b1 = val(perfB, t0, True), val(perfB, t1, False)
            d0, d1 = a0 - b0, a1 - b1
            tramos = [(t0, t1, d0, d1)]
            if d0 * d1 < 0:                               # los perfiles se cruzan: se parte en el cruce
                tc = t0 + (t1 - t0) * d0 / (d0 - d1)
                tramos = [(t0, tc, d0, 0.0), (tc, t1, 0.0, d1)]
            for (s0, s1, e0, e1) in tramos:
                ha0, ha1 = val(perfA, s0, True), val(perfA, s1, False)
                hb0, hb1 = val(perfB, s0, True), val(perfB, s1, False)
                if max(e0, e1) > 0.005:                   # A más alta: la cara mira a B
                    tex = self._tex(A["pared"], "roca")
                    self._cara(ch, tex, P(s0), P(s1), hb0, hb1, ha0, ha1, nrm_hacia_B, self._esc_tex(tex),
                               interior=0.55 if B.get("techo") is not None else 0.0,
                               coll=max(e0, e1) > ESCALON, clo=B, cup=A)
                elif min(e0, e1) < -0.005:                # B más alta: la cara mira a A
                    tex = self._tex(B["pared"], "roca")
                    self._cara(ch, tex, P(s0), P(s1), ha0, ha1, hb0, hb1, tuple(-v for v in nrm_hacia_B),
                               self._esc_tex(tex), interior=intA, coll=max(-e0, -e1) > ESCALON, clo=A, cup=B)
        # ---- techos: faldón entre techos de distinta altura, o canto del techo hacia fuera ----
        cA = A.get("techo")
        cB = None if contra_vacio else B.get("techo")
        if cA is None and cB is None:
            return
        p0, p1 = P(0.0), P(1.0)
        g = self.grosor_techo
        if cA is not None and cB is not None:
            if abs(cA - cB) < 0.005:
                return
            if cA < cB:      # la cara se ve desde B
                tex = self._tex(A["ttex"], "muro")
                self._cara(ch, tex, p0, p1, cA, cA, cB, cB, nrm_hacia_B, self._esc_tex(tex), interior=0.55)
            else:
                tex = self._tex(B["ttex"], "muro")
                self._cara(ch, tex, p0, p1, cB, cB, cA, cA, tuple(-v for v in nrm_hacia_B), self._esc_tex(tex),
                           interior=0.55)
            return
        # solo una tiene techo: si la otra es un muro que llega hasta el techo, ya está tapado
        if cA is not None:
            alto_B = -1e9 if contra_vacio else max(h for tr in self.perfil(B, opuesto) for h in tr[2:])
            if alto_B < cA - 0.005:
                tex = self._tex(A["ttex"], "muro")
                self._cara(ch, tex, p0, p1, cA, cA, cA + g, cA + g, nrm_hacia_B, self._esc_tex(tex))
        else:
            alto_A = max(h for tr in perfA for h in tr[2:])
            if alto_A < cB - 0.005:
                tex = self._tex(B["ttex"], "muro")
                self._cara(ch, tex, p0, p1, cB, cB, cB + g, cB + g, tuple(-v for v in nrm_hacia_B),
                           self._esc_tex(tex))

    def _escalera(self, ch, c, x0, y0):
        """Huellas y tabicas de una casilla de escalera; la colisión es la rampa."""
        C = self.celda
        tex = self._tex(c["tex"], "losas")
        texp = self._tex(c["pared"], "sillar")
        n = self._pasos(c)
        f0, f1, d = c["f0"], c["f1"], c["dir"]
        dz = (f1 - f0) / n
        up = (0.0, 0.0, 1.0)
        inter = 0.55 if c.get("techo") is not None else 0.0
        e = self._esc_tex(tex)
        for k in range(n):
            u0, u1 = k / n, (k + 1) / n
            h0, h1 = f0 + k * dz, f0 + (k + 1) * dz
            # rectángulo de la huella k en coordenadas del mundo
            if d == "N":
                r = (x0, y0 + u0 * C, x0 + C, y0 + u1 * C); fr = ((x0, y0 + u0 * C), (x0 + C, y0 + u0 * C)); nf = (0, -1, 0)
            elif d == "S":
                r = (x0, y0 + (1 - u1) * C, x0 + C, y0 + (1 - u0) * C); fr = ((x0 + C, y0 + (1 - u0) * C), (x0, y0 + (1 - u0) * C)); nf = (0, 1, 0)
            elif d == "E":
                r = (x0 + u0 * C, y0, x0 + u1 * C, y0 + C); fr = ((x0 + u0 * C, y0 + C), (x0 + u0 * C, y0)); nf = (-1, 0, 0)
            else:
                r = (x0 + (1 - u1) * C, y0, x0 + (1 - u0) * C, y0 + C); fr = ((x0 + (1 - u0) * C, y0), (x0 + (1 - u0) * C, y0 + C)); nf = (1, 0, 0)
            a, b = (r[0], r[1], h1), (r[2], r[1], h1)
            cc, dd = (r[2], r[3], h1), (r[0], r[3], h1)
            uv = tuple((p[0] / e, p[1] / e) for p in (a, b, cc, dd))
            cols = [self.luzv(p, up, inter, 0.0, c) for p in (a, b, cc, dd)]
            self.geo.quad(ch, tex, a, b, cc, dd, *uv, *cols, up, cerca=True)
            # tabica (de h0 a h1) en el borde de arranque de la huella
            self._cara(ch, texp, fr[0], fr[1], h0, h0, h1, h1, nf, self._esc_tex(texp), interior=inter, clo=c, cup=c)
        h00, h10, h11, h01 = c["esq"]
        self.geo.cquad(ch, "floor", (x0, y0, h00), (x0 + C, y0, h10), (x0 + C, y0 + C, h11), (x0, y0 + C, h01))

    def colision_suelos(self):
        """Suelo de la colisión con pocas tiras: las casillas planas a la misma altura se juntan en
        rectángulos (de 4 x 4 casillas como mucho) y las inclinadas en tiras por filas. El sitio para la
        colisión en 099.map es pequeño (unos 180 KB) y una tira por casilla no cabía en mapas grandes."""
        C = self.celda
        hecho = set()
        celdas = self.suelos_coll

        def plana(k):
            e = celdas.get(k)
            return e is not None and max(e) - min(e) < 1e-4

        for (i, j) in sorted(celdas, key=lambda k: (k[1], k[0])):
            if (i, j) in hecho or not plana((i, j)):
                continue
            h = celdas[(i, j)][0]
            ch = ("G", i // self.trozo, j // self.trozo)
            mismo = lambda ii, jj: ((ii, jj) not in hecho and plana((ii, jj)) and abs(celdas[(ii, jj)][0] - h) < 1e-4
                                    and ii // self.trozo == i // self.trozo and jj // self.trozo == j // self.trozo)
            w = 1
            while w < 4 and mismo(i + w, j):
                w += 1
            hgt = 1
            while hgt < 4 and all(mismo(i + k, j + hgt) for k in range(w)):
                hgt += 1
            for jj in range(j, j + hgt):
                for ii in range(i, i + w):
                    hecho.add((ii, jj))
            x0, y0 = self.ox + i * C, self.oy + j * C
            x1, y1 = x0 + w * C, y0 + hgt * C
            self.geo.cquad(ch, "floor", (x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h))
        # las inclinadas: tiras a lo largo de x (hasta 14 casillas: 30 puntos, como en los mapas originales)
        for (i, j) in sorted(celdas, key=lambda k: (k[1], k[0])):
            if (i, j) in hecho:
                continue
            ch = ("G", i // self.trozo, j // self.trozo)
            fila = [i]
            while len(fila) < 14 and (fila[-1] + 1, j) in celdas and (fila[-1] + 1, j) not in hecho \
                    and (fila[-1] + 1) // self.trozo == i // self.trozo and not plana((fila[-1] + 1, j)):
                fila.append(fila[-1] + 1)
            pts = []
            y0, y1 = self.oy + j * C, self.oy + (j + 1) * C
            for k, ii in enumerate(fila):
                h00, h10, h11, h01 = celdas[(ii, j)]
                x0 = self.ox + ii * C
                if k == 0:
                    pts += [(x0, y0, h00), (x0, y1, h01)]
                pts += [(x0 + C, y0, h10), (x0 + C, y1, h11)]
                hecho.add((ii, j))
            self.geo.coll[ch]["floor"].append(pts)

    def juntar_paredes(self):
        """Junta en una sola las paredes de colisión verticales y seguidas (misma línea y mismas alturas)."""
        for ch, kinds in self.geo.coll.items():
            if not (isinstance(ch, tuple) and ch and ch[0] == "G"):
                continue
            grupos, resto = {}, []
            for poly in kinds["wall"]:
                if len(poly) != 4:
                    resto.append(poly)
                    continue
                a, b, d, c = poly           # cquad guarda [a, b, d, c]: a-b abajo, d-c arriba
                if not (abs(a[2] - b[2]) < 1e-4 and abs(c[2] - d[2]) < 1e-4 and abs(a[0] - d[0]) < 1e-4
                        and abs(a[1] - d[1]) < 1e-4 and abs(b[0] - c[0]) < 1e-4 and abs(b[1] - c[1]) < 1e-4):
                    resto.append(poly)
                    continue
                if abs(a[1] - b[1]) < 1e-4:
                    clave, t0, t1 = ("x", round(a[1], 3), round(a[2], 3), round(d[2], 3)), a[0], b[0]
                elif abs(a[0] - b[0]) < 1e-4:
                    clave, t0, t1 = ("y", round(a[0], 3), round(a[2], 3), round(d[2], 3)), a[1], b[1]
                else:
                    resto.append(poly)
                    continue
                grupos.setdefault(clave, []).append((min(t0, t1), max(t0, t1)))
            nuevas = []
            for (eje, linea, z0, z1), tramos in grupos.items():
                tramos.sort()
                cur = list(tramos[0])
                for t0, t1 in tramos[1:] + [(None, None)]:
                    if t0 is not None and t0 <= cur[1] + 1e-4 and t1 - cur[0] <= 12.5:
                        cur[1] = max(cur[1], t1)
                        continue
                    if eje == "x":
                        p0, p1 = (cur[0], linea), (cur[1], linea)
                    else:
                        p0, p1 = (linea, cur[0]), (linea, cur[1])
                    a, b = (p0[0], p0[1], z0), (p1[0], p1[1], z0)
                    nuevas.append([a, b, (p0[0], p0[1], z1), (p1[0], p1[1], z1)])
                    if t0 is not None:
                        cur = [t0, t1]
            kinds["wall"] = resto + nuevas

    def malla_kf(self, km):
        self.kf_nivel_agua = None
        import kf2_a_editor as ka
        import kf_malla
        try:      # MO.T: los modelos de los objetos de decorado (barriles, mesas, la fuente...)
            arch = ka.leer_archivos(km["ruta"], ("FDAT.T", "RTIM.T", "RTMD.T", "MO.T"))
        except FileNotFoundError:
            arch = ka.leer_archivos(km["ruta"])
        datos = kf_malla.Datos(arch, km["juego"], int(km["nivel"]))
        # para el pulpo (el Kraken, kf4_pulpo): su modelo de MO.T y la memoria de vídeo del nivel (sus texturas)
        self.kf_mo = arch.get("MO.T") if km["juego"] == "kf1" else None
        self.kf_vram = datos.vram
        pad_ = int(km["pad"])
        self.kf_props = len(datos.props)
        self.kf_fuentes = []          # fuentes que curan: (x, y, z) del editor
        for (col, fila, ffx, ffz) in datos.fuentes:
            fx_ = self.ox + (col + pad_ + ffz) * self.celda
            fy_ = self.oy + (fila + pad_ + ffx) * self.celda
            self.kf_fuentes.append((fx_, fy_, self.altura(fx_, fy_)))
        atlas = kf_malla.Atlas(TEXTURAS, kf_malla.campos_huecos(TEXTURAS))
        # la colisión, de la rejilla (como en el PS1, que choca por casillas): la del mapa de bloques, que es
        # compacta; de ese mapa solo se queda la colisión, lo que se ve son los modelos de verdad
        self.terreno(self.tapadas)
        self.geo.render.clear()
        # la colisión ya no sale de la rejilla (las casillas del King's Field casi nunca son un bloque: muelles,
        # escaleras, orillas en diagonal, agua poco profunda...): es la geometría de verdad de los modelos
        # (kf_malla._es_colision). La rejilla queda para la altura de enemigos, objetos y el inicio.
        kf_malla.FORZAR_PARTIR.clear()
        for intento in range(4):
            self.geo.coll.clear()
            self.geo.render.clear()
            atlas = kf_malla.Atlas(TEXTURAS, kf_malla.campos_huecos(TEXTURAS))
            self.kf_plantillas, sin_sitio, tris = kf_malla.construir(self, datos, float(km["h0"]), atlas,
                                                                      int(km["pad"]), colision=True)
            # ningún registro puede pasar de 1008 puntos de colisión (scratchpad): si alguno pasa, su trozo de 8
            # se parte más fino y se vuelve a montar
            grandes = [ch for ch, n in kf_malla.puntos_por_trozo(self).items() if n > 950]
            if not grandes:
                break
            pad = int(km["pad"])
            for ch in grandes:
                lado = {"G": 8, "H": 4, "I": 2}.get(ch[0], 8)
                k8 = (ch[1] * lado // 8, ch[2] * lado // 8)
                kf_malla.FORZAR_PARTIR[k8] = 4 if lado == 8 else 2
        self.kf_atlas = atlas
        self.kf_info = (len(atlas.sitio), sin_sitio, tris)
        self.kf_ocultas = kf_malla.ULTIMAS_OCULTAS

    def terreno(self, tapadas):
        n, C = self.n, self.celda
        self.suelos_coll = {}
        for j in range(n):
            for i in range(n):
                A = self.celda_en(i, j)
                if not isinstance(A, dict):
                    continue
                x0, y0 = self.ox + i * C, self.oy + j * C
                ch = ("G", i // self.trozo, j // self.trozo)
                h00, h10, h11, h01 = A["esq"]
                a, b = (x0, y0, h00), (x0 + C, y0, h10)
                cc, d = (x0 + C, y0 + C, h11), (x0, y0 + C, h01)
                inter = 0.55 if A.get("techo") is not None else 0.0
                if A["tipo"] == "escalera":
                    self._escalera(ch, A, x0, y0)
                elif A.get("tapa") is False:
                    pass
                else:
                    tex = self._tex(A["tex"], "losas")
                    nrm = norm(cross(sub(b, a), sub(d, a)))
                    if nrm[2] < 0:
                        nrm = (-nrm[0], -nrm[1], -nrm[2])
                    e = self._esc_tex(tex)
                    uv = tuple((p[0] / e, p[1] / e) for p in (a, b, cc, d))
                    cols = [self.luzv(p, nrm, inter, 0.0, A) for p in (a, b, cc, d)]
                    self.geo.quad(ch, tex, a, b, cc, d, *uv, *cols, nrm)
                    subida = max(abs(a[2] - b[2]), abs(b[2] - cc[2]), abs(cc[2] - d[2]), abs(d[2] - a[2])) / C
                    if subida > PENDIENTE_MURO:
                        self.geo.cquad(ch, "wall", a, b, cc, d)
                    else:
                        self.suelos_coll[(i, j)] = A["esq"]      # se juntan luego en rectángulos y tiras
                if A.get("techo") is not None:
                    t = A["techo"]
                    tt = self._tex(A["ttex"], "muro")
                    e = self._esc_tex(tt)
                    pts = [(x0, y0, t), (x0, y0 + C, t), (x0 + C, y0 + C, t), (x0 + C, y0, t)]
                    dn = (0.0, 0.0, -1.0)
                    self.geo.quad(ch, tt, *pts, *[(p[0] / e, p[1] / e) for p in pts],
                                  *[self.luzv(p, dn, 0.55) for p in pts], dn, cerca=True)
                    if self.cubierta:
                        g = self.grosor_techo
                        pts = [(x0, y0, t + g), (x0 + C, y0, t + g), (x0 + C, y0 + C, t + g), (x0, y0 + C, t + g)]
                        self.geo.quad(ch, tt, *pts, *[(p[0] / e, p[1] / e) for p in pts],
                                      *[self.luzv(p, (0, 0, 1)) for p in pts], (0.0, 0.0, 1.0))
                # aristas: cada una se trata una vez desde la celda de abajo/izquierda, y contra el vacío
                # desde la celda que existe
                for lado, (vi, vj), p0, p1, nrm_b in (
                        ("N", (i, j + 1), (x0, y0 + C), (x0 + C, y0 + C), (0.0, 1.0, 0.0)),
                        ("E", (i + 1, j), (x0 + C, y0), (x0 + C, y0 + C), (1.0, 0.0, 0.0)),
                        ("S", (i, j - 1), (x0, y0), (x0 + C, y0), (0.0, -1.0, 0.0)),
                        ("W", (i - 1, j), (x0, y0), (x0, y0 + C), (-1.0, 0.0, 0.0))):
                    B = self.celda_en(vi, vj)
                    if B == "tapada":
                        continue
                    if B is None:
                        self._caras_arista(ch, A, None, lado, p0, p1, nrm_b, True)
                    elif lado in ("N", "E"):
                        self._caras_arista(ch, A, B, lado, p0, p1, nrm_b, False)
        self.colision_suelos()
        self.juntar_paredes()

    # ---- piezas ----
    def volcar(self, tmp, idx, pos, ang):
        """Mueve la geometría de una pieza (hecha en el origen) a su sitio en el mapa."""
        def P(p):
            x, y = girar(p, ang)
            return (x + pos[0], y + pos[1], p[2] + pos[2])

        def N(n):
            x, y = girar(n, ang)
            return (x, y, n[2])
        for ch, por_tex in tmp.geo.render.items():
            destino = ("O", idx) + tuple(ch)
            for tex, tiras in por_tex.items():
                for tira in tiras:
                    vs = []
                    for v in tira:
                        q = P(v[0])
                        m = self.color_en(q[0], q[1])      # el color pintado en el suelo tiñe también las piezas
                        vs.append((q, v[1], tuple(clamp(v[2][k] * m[k], 0, 255) for k in range(3)), N(v[3])))
                    self.geo.strip(destino, tex, vs)
        for ch, kinds in tmp.geo.coll.items():
            destino = ("O", idx) + tuple(ch)
            for kind, polys in kinds.items():
                for poly in polys:
                    self.geo.coll[destino][kind].append([P(p) for p in poly])
        self.geo.trozos += tmp.geo.trozos

    def escaleras(self, b, ancho, largo, alto):
        """Escalinata a lo largo de +Y, de 0 a `largo`, subiendo `alto`, con muretes a los lados."""
        ch = ("E", 0)
        pasos = max(1, int(round(alto / 0.3)))
        w = ancho / 2
        for k in range(pasos):
            y0, y1 = largo * k / pasos, largo * (k + 1) / pasos
            z0, z1 = alto * k / pasos, alto * (k + 1) / pasos
            b.suelo(ch, kp.LOSA_IRR, (-w, y0, z1), (w, y0, z1), (w, y1, z1), (-w, y1, z1), esc=2.5, coll=False)
            b.q(ch, kp.LOSA_IRR, (w, y0, z0), (-w, y0, z0), (-w, y0, z1), (w, y0, z1),
                ((0, 0), (ancho / 2.5, 0), (ancho / 2.5, 0.12), (0, 0.12)), (0, -1, 0), k=0.75)
        b.geo.cquad(ch, "floor", (-w, 0, 0), (w, 0, 0), (w, largo, alto), (-w, largo, alto))
        for sx in (-1, 1):
            x_ = sx * w
            pa, pb = ((x_, 0.0), (x_, largo)) if sx > 0 else ((x_, largo), (x_, 0.0))
            b.pared(ch, kp.SILLAR, pa, pb, -1.5, alto + 0.8, esc=3.0)
            b.muro_coll(ch, pa, pb, -0.5, alto + 2.6)

    def pieza(self, idx, o):
        tipo = o.get("tipo")
        pr = o.get("params", {})
        ang = math.radians(float(o.get("rot", 0.0)))
        x, y = float(o["x"]), float(o["y"])
        if tipo == "casa":
            # la casa se alinea con la rejilla del terreno (giro de 90 en 90): así su suelo encaja con las
            # celdas sin huecos ni suelos solapados
            ang = math.radians(round(float(o.get("rot", 0.0)) / 90.0) * 90.0)
            w, d = float(pr.get("ancho", 5.0)), float(pr.get("fondo", 7.5))
            if round(math.degrees(ang) / 90.0) % 2:
                w, d = d, w
            x = self.ox + round((x - w / 2 - self.ox) / self.celda) * self.celda + w / 2
            y = self.oy + round((y - d / 2 - self.oy) / self.celda) * self.celda + d / 2
        z = float(o["z"]) if o.get("z") is not None else self.altura(x, y)
        b = Constructor(self.semilla + idx)
        if tipo == "casa":
            w, d = float(pr.get("ancho", 5.0)), float(pr.get("fondo", 7.5))
            h = float(pr.get("alto", 7.0))
            c = {"nombre": f"c{idx}", "x0": -w / 2, "x1": w / 2, "y0": -d / 2, "y1": d / 2, "alto": h,
                 "puerta": pr.get("puerta", "N"), "cumbre": float(pr.get("cumbre", 4.5)),
                 "ruina": bool(pr.get("ruina", False)), "hundido": bool(pr.get("hundido", False)),
                 "ventanas": [("E", 0.35, h * 0.6), ("W", 0.5), ("W", 0.3, h * 0.6), ("E", 0.7, h * 0.6)]}
            if pr.get("chimenea", True):
                c["chimenea"] = (0.0, -d / 2 - 0.8)
                c["chimenea_alto"] = float(pr.get("chimenea_alto", 7.0))
            b.casa(c)
            # celdas del terreno que tapa la casa
            for i in range(self.n):
                for j in range(self.n):
                    cxw = self.ox + (i + 0.5) * self.celda - x
                    cyw = self.oy + (j + 0.5) * self.celda - y
                    lx, ly = girar((cxw, cyw), -ang)
                    if abs(lx) < w / 2 and abs(ly) < d / 2:
                        self.tapadas.add((i, j))
            self.casas.append({"x": x, "y": y, "z": z})
        elif tipo == "columna":
            alto = float(pr.get("alto", 8.0))
            b.prisma(("P", 0), kp.ESTRIA, (0.0, 0.0), float(pr.get("radio", 0.6)), -0.3, alto, lados=8, esc=3.0,
                     coll=2.6, roto=0.6 if pr.get("rota") else 0.0)
        elif tipo == "murete":
            L = float(pr.get("largo", 5.0))
            b.murete((-L / 2, 0.0), (L / 2, 0.0), alto=float(pr.get("alto", 0.9)))
        elif tipo == "portal":
            w = float(pr.get("ancho", 13.0)) / 2
            h = float(pr.get("alto", 16.0))
            for sx in (-1, 1):
                b.prisma(("P", 1), kp.ESTRIA, (sx * w, 0.0), 0.8, -0.2, h + 0.4, lados=8, esc=4.0, coll=2.6)
            ch = ("P", 1)
            for (p0, p1, n) in (((-w - 0.9, -0.8), (w + 0.9, -0.8), (0, -1, 0)), ((w + 0.9, 0.8), (-w - 0.9, 0.8), (0, 1, 0))):
                b.q(ch, kp.BANDA, (p0[0], p0[1], h), (p1[0], p1[1], h), (p1[0], p1[1], h + 1.6), (p0[0], p0[1], h + 1.6),
                    ((0, 0), (w / 2, 0), (w / 2, 0.4), (0, 0.4)), n)
            b.q(ch, kp.BANDA, (-w - 0.9, 0.8, h), (w + 0.9, 0.8, h), (w + 0.9, -0.8, h), (-w - 0.9, -0.8, h),
                ((0, 0), (w / 2, 0), (w / 2, 0.4), (0, 0.4)), (0, 0, -1), k=0.4)
            b.q(ch, kp.BANDA, (-w - 0.9, -0.8, h + 1.6), (w + 0.9, -0.8, h + 1.6), (w + 0.9, 0.8, h + 1.6),
                (-w - 0.9, 0.8, h + 1.6), ((0, 0), (w / 2, 0), (w / 2, 0.4), (0, 0.4)), (0, 0, 1))
        elif tipo == "puente":
            largo, w = float(pr.get("largo", 60.0)), float(pr.get("ancho", 5.0))
            for i in range(self.n):          # el tablero tapa las celdas del terreno que pisa
                for j in range(self.n):
                    lx, ly = girar((self.ox + (i + 0.5) * self.celda - x, self.oy + (j + 0.5) * self.celda - y), -ang)
                    if abs(lx) < w / 2 and 0 < ly < largo:
                        self.tapadas.add((i, j))
            b.puente_y0, b.puente_y1 = 0.0, float(pr.get("largo", 60.0))
            b.puente_z0, b.puente_z1 = 0.0, float(pr.get("subida", 0.0))
            b.puente_ancho = float(pr.get("ancho", 5.0))
            b.puente()
        elif tipo == "barbacana":
            b.barb_y0, b.barb_fondo, b.puente_z1 = 0.0, 12.0, 0.0
            b.barbacana()
        elif tipo == "torre":
            b.torre_r = float(pr.get("radio", 115.0))
            b.torre_c = (0.0, 0.0)
            b.torre()
        elif tipo == "ruina":
            b.ruina_columnas((0.0, 0.0), float(pr.get("lado", 18.0)), 0.0, pisos=int(pr.get("pisos", 3)))
        elif tipo == "escaleras":
            self.escaleras(b, float(pr.get("ancho", 3.0)), float(pr.get("largo", 6.0)), float(pr.get("alto", 3.0)))
        else:
            return
        self.volcar(b, idx, (x, y, z), ang)

    # ---- montaje ----
    def construir(self):
        m = self.mapa
        self.n = int(m["n"])
        self.celda = float(m.get("celda", 2.5))
        self.ox, self.oy = (float(v) for v in m.get("origen", [-self.n * self.celda / 2] * 2))
        self.alturas = m["alturas"]
        self.texturas = m["texturas"]
        self.paleta = m.get("paleta", ["vacio"] + list(TEXTURAS))
        self.tapadas = set()
        self.cache = {}
        # tamaño de los trozos (registros) del terreno: 8 x 8 casillas, o más en mapas grandes para que
        # no pasen de unos 110 registros (la tabla de registros de 099.map tiene sitio limitado)
        self.trozo = max(8, math.ceil(self.n / 10.5))
        if m.get("kf_malla"):     # mapas portados: trozos de 8 casillas; con las paredes de verdad en la colisión,
            self.trozo = 8        # uno de 16 pasaba de los 1008 puntos que caben en el scratchpad (0x70000100..)
        self.construidas = {}
        self.techos_terreno = {}
        for clave, c in (m.get("celdas") or {}).items():
            i, j = (int(v) for v in clave.split(","))
            if c.get("terreno"):                 # solo un techo sobre una celda de terreno
                self.techos_terreno[(i, j)] = c
            else:
                self.construidas[(i, j)] = c
        self.colores = m.get("colores")
        self.escala_tex = float(m["escala_tex"]) if m.get("escala_tex") else None
        self.texturas_kf2 = {}
        for nombre, b64 in (m.get("texturas_kf2") or {}).items():
            if nombre in TEXTURAS:
                import base64
                import io
                import numpy as np
                from PIL import Image
                self.texturas_kf2[TEXTURAS[nombre]] = np.asarray(
                    Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA"))
        self.paredes = m.get("paredes")
        self.pared_terreno = m.get("pared_terreno", "roca")
        self.borde_prof = float(m.get("borde_prof", 10.0))
        self.grosor_techo = float(m.get("grosor_techo", 0.6))
        self.cubierta = bool(m.get("cubierta", False))
        self.barandilla = bool(m.get("barandilla", True))
        # la banda donde se trocean los triángulos cerca de la cámara sigue las alturas del mapa
        hs = [float(h) for h in self.alturas] + [float(c.get("f", 0)) for c in self.construidas.values()]
        hs += [float(v) for c in self.construidas.values() if c.get("esc") for v in c["esc"][1:3]]
        self.geo.banda = (min(hs) - 6.0, max(hs) + 16.0)
        self.luz.fuentes = []
        for idx, o in enumerate(m.get("objetos", [])):
            self.pieza(idx, o)
        self.kf_atlas = None
        self.cielo = bool(m.get("cielo", False))     # domo de nubes del 4 (mapas con zonas al aire libre)
        km = m.get("kf_malla")
        if km:          # la geometría real de un mapa de King's Field de PS1 (kf_malla.py)
            self.malla_kf(km)
        else:
            self.terreno(self.tapadas)
        ini = m.get("inicio", {"x": 0.0, "y": 0.0})
        sx, sy = float(ini["x"]), float(ini["y"])
        p = (sx, sy, self.altura(sx, sy))
        self.intro = [p, p, p]
        self.inicio = p
        g = m.get("guardado")
        self.guardado = (float(g["x"]), float(g["y"]), self.altura(float(g["x"]), float(g["y"]))) if g else None
        def z_de(e):          # "z" la trae un mapa portado (la altura de la capa donde está); si no, el suelo
            if e.get("agua") and getattr(self, "kf_nivel_agua", None) is not None:
                return self.kf_nivel_agua - PEZ_HONDO       # los peces: bajo la superficie del agua
            if e.get("sobre_agua") and getattr(self, "kf_nivel_agua", None) is not None:
                return self.kf_nivel_agua + 1.5             # los que vuelan sobre el agua
            z = float(e["z"]) if e.get("z") is not None else self.altura(float(e["x"]), float(e["y"]))
            return z + (2.5 if e.get("vuela") else 0.0)
        self.objetos = [(int(it["id"]), (float(it["x"]), float(it["y"]), z_de(it))) for it in m.get("items", [])]
        self.enemigos = [(e.get("tipo", "escarabajo"), (float(e["x"]), float(e["y"]), z_de(e)))
                         for e in m.get("enemigos", [])]
        # la gente que habla de un mapa portado (kf1_npc): van como un enemigo más (su registro de gente del IV) y
        # kf4_valle les pone su conversación (guion_npcs) y su tienda
        self.kf_npcs = []
        for n_ in m.get("npcs", []) or []:
            pos_ = (float(n_["x"]), float(n_["y"]), z_de(n_))
            self.enemigos.append((f"chr:{int(n_['registro'])}", pos_))
            self.kf_npcs.append(dict(n_, pos=pos_))
        self.tiendas_kf1 = {int(k): list(v_) for k, v_ in (m.get("tiendas_kf1") or {}).items()}
        self.spawns_pos = [p for _, p in self.enemigos]
        # hacia dónde mira cada enemigo al aparecer (el giro del mapa, como los cofres; sin él, al azar)
        self.giros = {(float(e["x"]), float(e["y"]), z_de(e)): float(e["giro"])
                      for e in list(m.get("enemigos", [])) + list(m.get("npcs", []) or []) if e.get("giro") is not None}
        # cambios de nivel de un mapa portado (kf4_valle.guion_niveles): salidas (área en el suelo y nivel al que
        # llevan) y dónde se aparece al venir de cada nivel
        self.kf_nivel = int((m.get("kf_malla") or {}).get("nivel", -1))
        self.kf_salidas = [dict(s_) for s_ in m.get("salidas", []) if isinstance(s_, dict)]
        self.kf_llegadas = {int(k): dict(v_) for k, v_ in (m.get("llegadas") or {}).items()}
        # cofres, puertas y paredes que se abren de un mapa portado (kf4_valle.colocar_objetos_kf)
        self.kf_objetos = [{"tipo": o["tipo"], "pos": (float(o["x"]), float(o["y"]), z_de(o)),
                            "giro": float(o.get("giro", 0.0)), "medida": o.get("medida"),
                            "objeto": int(o.get("objeto", 0)), "kf": o.get("kf"), "llave": int(o.get("llave", 0)),
                            "nicho": bool(o.get("nicho"))}
                           for o in m.get("kf_objetos", []) if isinstance(o, dict) and o.get("tipo")]
