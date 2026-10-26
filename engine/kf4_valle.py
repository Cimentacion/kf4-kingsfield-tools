#!/usr/bin/env python3
"""
kf4_valle.py - Genera la zona 1 del randomizador de King's Field IV: un valle en un acantilado.

Caminos estrechos colgados del muro, el muro sigue hasta perderse arriba y abajo, casas excavadas
en la roca con puertas y ventanas iluminadas, un puente entre las dos paredes y escaleras.
Toda la geometría es nueva (generada aquí) pero usa las texturas reales de North Cliffs (031)
y el formato de mapa original: piezas OMD con vertex colors horneados, colisión CSK, registros
con sus cajas y niebla. El mapa resultante sustituye a 099 (el mapa donde empieza Partida nueva).

Uso:
    python kf4_valle.py                         usa la .iso junto al script, semilla 1
    python kf4_valle.py "King's Field IV.iso" --semilla 7
    python kf4_valle.py --solo-mapa             no toca la ISO: solo escribe kf4_valle/099.map
    python kf4_valle.py --rumbo 3.1416          cambia hacia dónde mira el jugador al empezar
    python kf4_valle.py --debug                 Partida nueva con el ini de debug 9999 (dash, nivel alto)
    python kf4_valle.py --giro 2.2              velocidad de giro de la cámara (1 = la original; 2.2 por defecto)
    python kf4_valle.py --debug 5000            o con otro ini de desarrollo (ver kf4_patch.py --list)
    (o simplemente doble clic en JUGAR_VALLE.bat: genera, inyecta y abre PCSX2)

Salida (carpeta kf4_valle/ junto al script):
    099.map                       el mapa nuevo
    resumen.txt                   tamaños, triángulos, spawns, lo que se ha hecho
    King's Field IV (valle).iso   copia de la ISO con el 099 nuevo en los 5 idiomas (junto a la ISO original)

Necesita kf4_mapdump.py en la misma carpeta. Solo librería estándar (Python 3.8+).
"""

import os
import sys
import math
import shutil
import struct
import random
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kf4_mapdump as md  # noqa: E402
import kf4_pulpo  # noqa: E402

# ======================= Texturas de North Cliffs (031) por (TBP, CBP) =======================
ROCA = (0x32C0, 0x3D43)        # roca gris oscura 512
ROCA_VERDE = (0x3040, 0x3D42)  # roca verdosa 512
ROCA_PEQ = (0x2EC0, 0x3D45)    # roca verdosa 256
YESO = (0x2E40, 0x3D44)        # yeso agrietado con molduras arriba y abajo
FRISO = (0x2F80, 0x3D41)       # banda ornamental
LADRILLO_OSC = (0x2FC0, 0x3D48)
LOSAS = (0x3540, 0x3D46)       # losas de piedra (suelos)
RELIEVE = (0x37C0, 0x3D47)     # piedra grabada
LADRILLO = (0x3860, 0x3D60)    # ladrillo (fachadas de casas)
VIGA = (0x3A60, 0x3D49)        # banda / viga

# ======================= Parámetros del valle (metros, Z arriba, Y a lo largo del valle) =======================
COL = 2.5            # ancho de columna de la rejilla del muro
FILA = 1.5           # alto de fila en la banda fina
FINO_Z = (-15.0, 33.0)
Z_MIN, Z_MAX = -230.0, 260.0
Y_MIN, Y_MAX = -25.0, 245.0
CRECE = 1.75         # cada fila lejana es 1.75 veces la anterior
UV_TRAMO = 5.0      # unidades de UV que puede abarcar una tira (el límite real es ±8)
TROZO_MAX = 2.6      # lado máximo de un trozo de geometría a la altura de los caminos (m)
BANDA_CERCA = (-4.0, 16.0)   # alturas donde puede estar la cámara (cornisas, casas, escaleras)
FILA_MAX = 30.0      # tope (para que la textura no se salga de rango)
ANCHO_CORNISA = 3.75
CHUNK_Y = 35.0
FOG_RGB = (10, 12, 16)

VRAM_TEX_OFF_SRC = "031.map"
BASE_MAP = "099.map"


# ======================= Ruido =======================
class Ruido:
    def __init__(self, semilla):
        self.s = semilla * 2654435761 & 0xFFFFFFFF

    def _h(self, i, j, k=0):
        n = (i * 374761393 + j * 668265263 + k * 2147483647 + self.s) & 0xFFFFFFFF
        n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
        return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0

    def v(self, x, y, k=0):
        i, j = math.floor(x), math.floor(y)
        fx, fy = x - i, y - j
        fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        a, b = self._h(i, j, k), self._h(i + 1, j, k)
        c, d = self._h(i, j + 1, k), self._h(i + 1, j + 1, k)
        return (a + (b - a) * fx) + ((c + (d - c) * fx) - (a + (b - a) * fx)) * fy

    def fbm(self, x, y, k=0, oct=4):
        t, amp, f, norm = 0.0, 1.0, 1.0, 0.0
        for o in range(oct):
            t += amp * (self.v(x * f, y * f, k + o * 17) * 2 - 1)
            norm += amp
            amp *= 0.5
            f *= 2.03
        return t / norm


# ======================= Vectores =======================
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def norm(a):
    l = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    return (a[0] / l, a[1] / l, a[2] / l) if l > 1e-9 else (0.0, 0.0, 1.0)


def clamp(x, a, b):
    return a if x < a else b if x > b else x


# Desplazamiento global en el espacio del juego: el valle se coloca donde estaba el Palacio de Oath,
# para que la intro original, la cabecera y las partidas guardadas en 099 caigan sobre el camino.
OFFSET = [0.0, 0.0, 0.0]
INTRO_099 = (-5265.0, 0.0, -12184.0)    # primer MovePlayerTo de la intro original


def to_native(p):
    """Blender (m, Z arriba) -> espacio del juego (cm, Y hacia abajo), con el desplazamiento global."""
    return (p[0] * 100.0 + OFFSET[0], -p[2] * 100.0 + OFFSET[1], p[1] * 100.0 + OFFSET[2])


def fijar_offset(valle):
    """El punto A de la intro del valle coincide con el de la intro original de 099."""
    a = valle.intro[0]
    OFFSET[0] = INTRO_099[0] - a[0] * 100.0
    OFFSET[1] = INTRO_099[1] + a[2] * 100.0
    OFFSET[2] = INTRO_099[2] - a[1] * 100.0


# ======================= Almacén de geometría =======================
class Geo:
    """Por cada trozo (registro): tiras de render por textura y tiras de colisión por tipo."""

    def __init__(self):
        self.trozos = 0
        self.render = collections.defaultdict(lambda: collections.defaultdict(list))
        self.coll = collections.defaultdict(lambda: {"wall": [], "floor": []})

    def strip(self, chunk, tex, verts):
        """verts: lista de (pos, uv, color(r,g,b), normal). Tira de triángulos."""
        if len(verts) >= 3:
            self.render[chunk][tex].append(verts)

    def quad(self, chunk, tex, a, b, c, d, uva, uvb, uvc, uvd, ca, cb, cc, cd, n=None, cerca=True):
        """Cuadrilátero a-b-c-d en orden de contorno."""
        if n is None:
            n = norm(cross(sub(b, a), sub(d, a)))
        # El VU1 de KF4 tira los triángulos con una esquina fuera del rango del GS (p. ej. detrás de la
        # cámara) y solo los trocea una vez en 16: con triángulos grandes cerca del jugador se veían
        # huecos. Como en los mapas originales, todo lo que está a la altura de los caminos se
        # subdivide en trozos de TROZO_MAX metros como mucho.
        zs = (a[2], b[2], c[2], d[2])
        nu = nv = 1
        banda = getattr(self, "banda", BANDA_CERCA)     # el editor la amplía a las alturas de su mapa
        if cerca and min(zs) < banda[1] and max(zs) > banda[0]:
            nu = max(1, math.ceil(max(dist(a, b), dist(d, c)) / TROZO_MAX))
            nv = max(1, math.ceil(max(dist(a, d), dist(b, c)) / TROZO_MAX))
        # el rango de UV de una tira está limitado (±8): las caras muy grandes también se trocean
        span_s = max(abs(uvb[k] - uva[k]) for k in (0, 1))
        span_s = max(span_s, max(abs(uvc[k] - uvd[k]) for k in (0, 1)))
        span_t = max(abs(uvd[k] - uva[k]) for k in (0, 1))
        span_t = max(span_t, max(abs(uvc[k] - uvb[k]) for k in (0, 1)))
        nu = max(nu, math.ceil(span_s / UV_TRAMO))
        nv = max(nv, math.ceil(span_t / UV_TRAMO))
        if nu == 1 and nv == 1:
            self.strip(chunk, tex, [(a, uva, ca, n), (b, uvb, cb, n), (d, uvd, cd, n), (c, uvc, cc, n)])
            return
        self.trozos += nu * nv - 1
        filas_tira = max(1, int(UV_TRAMO // max(1e-6, span_t / nv)))

        def bil(pa, pb, pd, pc, s_, t_):
            return tuple((pa[k] + (pb[k] - pa[k]) * s_) * (1 - t_) + (pd[k] + (pc[k] - pd[k]) * s_) * t_
                         for k in range(len(pa)))
        for i in range(nu):
            s0, s1 = i / nu, (i + 1) / nu
            for j0 in range(0, nv, filas_tira):
                vs = []
                for j in range(j0, min(nv, j0 + filas_tira) + 1):
                    t = j / nv
                    for s_ in (s0, s1):
                        vs.append((bil(a, b, d, c, s_, t), bil(uva, uvb, uvd, uvc, s_, t),
                                   bil(ca, cb, cd, cc, s_, t), n))
                self.strip(chunk, tex, vs)

    def cquad(self, chunk, kind, a, b, c, d):
        self.coll[chunk][kind].append([a, b, d, c])

    def ctri(self, chunk, kind, a, b, c):
        self.coll[chunk][kind].append([a, b, c])


# ======================= Luz horneada =======================
class Luz:
    """Iluminación horneada en los vértices (así ilumina KF4 sus mapas: color por vértice x textura)."""
    LUNA = (0.28, 0.45, 0.85)   # luz fría que baja por la grieta del valle

    def __init__(self, ruido):
        self.r = ruido
        self.fuentes = []        # (centro, radio, fuerza): ventanas y puertas iluminadas
        l = math.sqrt(sum(c * c for c in self.LUNA))
        self.luna = tuple(c / l for c in self.LUNA)

    def estrato(self, y, z):
        """Estratos de la roca: índice de banda y distancia (0..0.5) al borde de la banda."""
        e = (z + 7.0 * self.r.fbm(y * 0.018, 0.5, 77, 3)) / 9.5
        k = math.floor(e)
        t = e - k
        return int(k), min(t, 1.0 - t)

    def roca(self, p, n, interior=0.0):
        up = n[2]
        sky = 0.60 + 0.34 * max(0.0, up) - 0.25 * max(0.0, -up)
        key = 0.30 * max(0.0, n[0] * self.luna[0] + n[1] * self.luna[1] + n[2] * self.luna[2])
        z = p[2]
        f = math.exp(-max(0.0, -z) / 65.0) * (1.0 - 0.35 * clamp((z - 25.0) / 160.0, 0, 1))
        var = 0.86 + 0.28 * self.r.v(p[1] * 0.35, z * 0.35, 91)
        churrete = 1.0 - 0.22 * clamp(self.r.v(p[1] * 0.55, z * 0.035, 57) * 2.2 - 1.2, 0, 1)   # manchas de humedad
        _, borde = self.estrato(p[1], z)
        veta = 1.0 - 0.30 * math.exp(-(borde / 0.045) ** 2)       # juntas oscuras entre estratos
        k = 1.10 * (sky + key) * f * var * churrete * veta * (1.0 - 0.45 * interior)
        r, g, b = 128 * k * 0.97, 128 * k * 0.99, 128 * k * 1.06   # roca algo fría
        # luz cálida que sale de ventanas y puertas
        for (c, rad, fu) in self.fuentes:
            dx, dy, dz = p[0] - c[0], p[1] - c[1], p[2] - c[2]
            if abs(dx) > rad or abs(dy) > rad or abs(dz) > rad:
                continue
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d < rad:
                w = fu * (1.0 - d / rad) ** 2
                r += 128 * w * 1.30
                g += 128 * w * 0.92
                b += 128 * w * 0.50
        return (clamp(r, 0, 255), clamp(g, 0, 255), clamp(b, 0, 255))

    def calida(self, p, centro, radio, fuerza=1.0, base=0.35):
        d = math.sqrt(sum((p[i] - centro[i]) ** 2 for i in range(3)))
        k = base + fuerza * max(0.0, 1.0 - d / radio)
        return (clamp(128 * k * 1.30, 0, 255), clamp(128 * k * 0.98, 0, 255), clamp(128 * k * 0.62, 0, 255))


# ======================= Trazado del valle =======================
class Valle:
    def __init__(self, semilla):
        self.semilla = semilla
        self.rng = random.Random(semilla)
        self.ruido = Ruido(semilla)
        self.luz = Luz(self.ruido)
        self.geo = Geo()
        r = self.rng
        self.fase = [r.uniform(0, 6.28) for _ in range(6)]
        # cornisas: lado, tramos (y0, y1, z) y rampas entre tramos (con escalones)
        self.cornisas = {
            "W": {"y0": 0.0, "y1": 220.0,
                  # el principio sigue el boceto: rellano de inicio, escaleras bajo un arco de roca, rellano
                  # en S, escaleras, callejón de casas y plataforma que gira hacia el vacío
                  "tramos": [(0.0, 7.5, 0.0), (15.0, 22.5, 3.0), (30.0, 107.5, 6.0), (117.5, 180.0, 3.0),
                             (195.0, 220.0, 10.5)]},
            "E": {"y0": 100.0, "y1": 175.0, "tramos": [(100.0, 175.0, 3.0)]},
        }
        self.puente = (125.0, 130.0, 3.0)
        self.arcos = [("W", 11.25)]          # arcos de roca que cruzan por encima del camino (lado, y)
        # aberturas: puertas (habitaciones) y ventanas; se rellenan en planificar()
        self.puertas = []
        self.ventanas = []
        self.spawns_pos = []
        self.items_pos = []
        self.casas = []
        self.inicio = None

    # ---- forma de los muros ----
    @staticmethod
    def _tramos_lineales(pts, y, fuera):
        if y <= pts[0][0] or y >= pts[-1][0]:
            return fuera
        for (ya, va), (yb, vb) in zip(pts, pts[1:]):
            if ya <= y <= yb:
                t = (y - ya) / (yb - ya) if yb > ya else 0.0
                return va + (vb - va) * t
        return fuera

    # El muro oeste avanza hacia el vacío en dos saltos (el camino hace la S del boceto) y luego vuelve
    DESP_W = [(17.5, 0.0), (20.0, 3.5), (52.5, 3.5), (55.0, 7.0), (70.0, 7.0), (77.5, 6.2), (85.0, 3.5),
              (92.5, 0.8), (97.5, 0.0)]
    # ancho de la cornisa oeste: rellanos anchos en los giros, callejón estrecho entre las casas
    ANCHO_W = [(15.0, ANCHO_CORNISA), (17.5, 7.25), (20.0, ANCHO_CORNISA), (30.0, ANCHO_CORNISA), (32.5, 2.75),
               (50.0, 2.75), (52.5, 7.25), (55.0, ANCHO_CORNISA)]

    def desp(self, lado, y):
        return self._tramos_lineales(self.DESP_W, y, 0.0) if lado == "W" else 0.0

    def ancho(self, lado, y):
        return self._tramos_lineales(self.ANCHO_W, y, ANCHO_CORNISA) if lado == "W" else ANCHO_CORNISA

    def base_x(self, lado, y):
        f = self.fase
        if lado == "W":
            return -14.0 + self.desp(lado, y) + 2.6 * math.sin(y / 37.0 + f[0]) + 1.2 * math.sin(y / 13.0 + f[1])
        return 14.0 + 2.4 * math.sin(y / 31.0 + f[2]) + 1.1 * math.sin(y / 11.0 + f[3])

    def inclin(self, z):
        """Los muros se cierran hacia arriba y hacia abajo: nunca se ve el final."""
        if z > 20:
            return 0.075 * (z - 20)
        if z < -20:
            return 0.05 * (-20 - z)
        return 0.0

    def muro_x(self, lado, y, z):
        s = 1.0 if lado == "W" else -1.0
        return self.base_x(lado, y) + s * self.inclin(z)

    def interior_dir(self, lado):
        return -1.0 if lado == "W" else 1.0   # hacia la roca

    def z_camino(self, lado, y):
        """Altura de la cornisa en y (None si no hay cornisa)."""
        c = self.cornisas[lado]
        if y < c["y0"] - 1e-6 or y > c["y1"] + 1e-6:
            return None
        tr = c["tramos"]
        for (a, b, z) in tr:
            if a - 1e-6 <= y <= b + 1e-6:
                return z
        for (a, b, z), (a2, b2, z2) in zip(tr, tr[1:]):
            if b < y < a2:
                return z + (z2 - z) * (y - b) / (a2 - b)
        return None

    def es_rampa(self, lado, y):
        tr = self.cornisas[lado]["tramos"]
        for (a, b, z), (a2, b2, z2) in zip(tr, tr[1:]):
            if b < y < a2:
                return True
        return False

    # ---- filas de la rejilla ----
    def filas(self):
        zs = []
        z = FINO_Z[0]
        while z <= FINO_Z[1] + 1e-6:
            zs.append(round(z, 4))
            z += FILA
        h = FILA
        z = zs[-1]
        while z < Z_MAX:
            h = min(FILA_MAX, h * CRECE)
            z = min(Z_MAX, z + h)
            zs.append(z)
        h = FILA
        z = zs[0]
        low = []
        while z > Z_MIN:
            h = min(FILA_MAX, h * CRECE)
            z = max(Z_MIN, z - h)
            low.append(z)
        return sorted(low) + zs

    def columnas(self):
        n = int(round((Y_MAX - Y_MIN) / COL))
        return [Y_MIN + i * COL for i in range(n + 1)]

    # ---- planificación: puertas, ventanas, enemigos ----
    def planificar(self):
        r = self.rng
        # casas (puertas en las cornisas): (lado, y0 de la columna, z del suelo, fondo, ancho en columnas, tipo)
        self.puertas = [
            # el callejón de casas del boceto
            {"lado": "W", "y": 32.5, "z": 6.0, "fondo": 6.0, "ancho": 2, "alto": 3.3, "tipo": "casa"},
            {"lado": "W", "y": 40.0, "z": 6.0, "fondo": 7.0, "ancho": 2, "alto": 3.6, "tipo": "casa"},
            {"lado": "W", "y": 47.5, "z": 6.0, "fondo": 6.5, "ancho": 2, "alto": 3.6, "tipo": "casa"},
            {"lado": "W", "y": 77.5, "z": 6.0, "fondo": 9.0, "ancho": 4, "alto": 4.2, "tipo": "sala"},
            {"lado": "W", "y": 150.0, "z": 3.0, "fondo": 6.0, "ancho": 3, "alto": 3.6, "tipo": "casa"},
            {"lado": "E", "y": 152.5, "z": 3.0, "fondo": 7.5, "ancho": 3, "alto": 3.6, "tipo": "casa"},
            {"lado": "E", "y": 107.5, "z": 3.0, "fondo": 5.0, "ancho": 3, "alto": 3.3, "tipo": "casa"},
            {"lado": "W", "y": 215.0, "z": 10.5, "fondo": 16.0, "ancho": 1, "alto": 3.0, "tipo": "tunel"},
        ]
        filas = self.filas()
        fino = [z for z in filas if FINO_Z[0] <= z <= FINO_Z[1] - FILA + 1e-6]
        cols = self.columnas()
        ocupado = set()

        def marca(lado, y, z0, nc, nf):
            for i in range(-1, nc + 1):
                for j in range(-1, nf + 1):
                    ocupado.add((lado, round(y + i * COL, 3), round(z0 + j * FILA, 3)))

        for p in self.puertas:
            marca(p["lado"], p["y"], p["z"], 1, 3)
        intentos = 0
        while len(self.ventanas) < 70 and intentos < 4000:
            intentos += 1
            lado = r.choice("WE")
            y = r.choice(cols[2:-3])
            z = r.choice(fino[1:-3])
            alto = r.choice([1, 1, 2])
            zc = self.z_camino(lado, y)
            zc2 = self.z_camino(lado, y + COL)
            # no tapar la cornisa: o bien por encima del camino + 1.5, o bien por debajo (en la cara de la cornisa)
            ok = True
            for zz in (zc, zc2):
                if zz is not None and (zz - 3.5 < z < zz + 1.5 or zz - 3.5 < z + alto * FILA < zz + 1.6):
                    ok = False
            if lado == "W" and 5 < y < 18 and -14 < z < 12:
                ok = False   # alrededor del arco de roca
            if (lado == "W" and 118 < y < 135) or (lado == "E" and 118 < y < 135):
                if -3 < z < 10:
                    ok = False   # alrededor del puente
            key = [(lado, round(y, 3), round(z + j * FILA, 3)) for j in range(alto)]
            if not ok or any(k in ocupado for k in key):
                continue
            marca(lado, y, z, 1, alto)
            luz = r.random() < 0.7
            self.ventanas.append({"lado": lado, "y": y, "z": z, "alto": alto, "luz": luz,
                                  "fondo": r.uniform(1.6, 2.6), "bajo_cornisa": zc is not None and z < zc})
        # spawns sobre las cornisas (13 en 099)
        puntos = []
        for lado, ys in (("W", [27, 36, 48, 62, 74, 92, 104, 140, 166, 186, 205]), ("E", [112, 140, 168])):
            for y in ys:
                z = self.z_camino(lado, y)
                if z is None:
                    continue
                x = self.muro_x(lado, y, z) - self.interior_dir(lado) * self.ancho(lado, y) * 0.55
                puntos.append((x, float(y), z))
        self.spawns_pos = puntos
        # enemigos de la zona 1 por tramos: plantas y escarabajos al principio, murciélagos y setas después
        r = self.rng
        plan = []
        sitios = []
        for lado, y0, y1, paso in (("W", 22, 215, 9.0), ("E", 106, 172, 11.0)):
            y = y0 + r.uniform(0, 3)
            while y < y1:
                if self.z_camino(lado, y) is not None and not self.es_rampa(lado, y) and \
                        not (self.puente[0] - 3 < y < self.puente[1] + 3):
                    sitios.append((lado, y))
                y += paso + r.uniform(-2, 3)
        for lado, y in sitios:
            z = self.z_camino(lado, y)
            x = self.muro_x(lado, y, z) - self.interior_dir(lado) * self.ancho(lado, y) * r.uniform(0.35, 0.7)
            if y < 70:
                tipo = r.choice(["planta", "planta", "escarabajo"])
            elif y < 150:
                tipo = r.choice(["murcielago", "escarabajo", "planta", "seta"])
            else:
                tipo = r.choice(["murcielago", "seta", "escarabajo"])
            if tipo == "murcielago":
                z += 2.5      # vuelan
            plan.append((tipo, (x, y, z)))
        self.enemigos = plan
        # la intro de Partida nueva: aparece en A, camina hasta B y la cámara corta a C
        mid = lambda y: (self.muro_x("W", y, 0.0) + self.ancho("W", y) * 0.5, y, 0.0)
        self.intro = [mid(2.0), mid(7.0), mid(8.0)]
        self.inicio = self.intro[-1]
        # fuentes de luz cálida para el horneado
        self.luz.fuentes = []
        for w in self.ventanas:
            if w["luz"]:
                c = (self.muro_x(w["lado"], w["y"] + COL / 2, w["z"]), w["y"] + COL / 2, w["z"] + w["alto"] * FILA / 2)
                self.luz.fuentes.append((c, 4.5, 0.55))
        for p in self.puertas:
            if p["tipo"] != "tunel":
                c = (self.muro_x(p["lado"], p["y"] + COL / 2, p["z"] + 1.5), p["y"] + COL / 2, p["z"] + 1.5)
                self.luz.fuentes.append((c, 6.0, 0.65))

    def chunk(self, lado, y):
        return (lado, int(math.floor((clamp(y, Y_MIN, Y_MAX - 0.01) - Y_MIN) / CHUNK_Y)))

    # ---- desplazamiento de la roca ----
    def plano(self, lado, y, z):
        """Cuánto se aplana la roca cerca de puertas y ventanas (0 = plano)."""
        m = 1.0
        for p in self.puertas:
            if p["lado"] != lado:
                continue
            dy = max(p["y"] - y, 0.0, y - (p["y"] + COL * (1 if p["tipo"] != "sala" else 1)))
            dz = max(p["z"] - z, 0.0, z - (p["z"] + 3 * FILA))
            m = min(m, clamp(max(dy, dz) / 2.5, 0, 1))
        for w in self.ventanas:
            if w["lado"] != lado:
                continue
            dy = max(w["y"] - y, 0.0, y - (w["y"] + COL))
            dz = max(w["z"] - z, 0.0, z - (w["z"] + w["alto"] * FILA))
            m = min(m, clamp(max(dy, dz) / 1.6, 0, 1))
        return m

    def roca_d(self, lado, y, z):
        """Hundimiento de la roca (positivo = hacia dentro). Ruido grande + escalones entre estratos."""
        n = self.ruido.fbm(y * 0.11, z * 0.11, 3 if lado == "W" else 7)
        n2 = self.ruido.fbm(y * 0.035, z * 0.03, 11 if lado == "W" else 13)
        amp = 1.3 + 2.0 * clamp((abs(z) - 20) / 120.0, 0, 1)
        banda, borde = self.luz.estrato(y, z)
        escalon = 0.55 * ((banda * 7) % 3) / 2.0 - 0.3          # cada estrato sobresale distinto
        d = (n * amp + n2 * 1.6 + escalon) * self.plano(lado, y, z)
        zc = self.z_camino(lado, y)
        if zc is not None and zc - 1.0 < z < zc + 3.0:
            d = max(d, -0.30)       # junto al camino la roca no invade el paso
        return d

    def punto_muro(self, lado, y, z, extra=0.0):
        s = self.interior_dir(lado)
        x = self.muro_x(lado, y, z) + s * (self.roca_d(lado, y, z) + extra)
        return (x, y, z)

    # ======================= Construcción =======================
    def construir(self):
        self.planificar()
        for lado in "WE":
            self.muro(lado)
            self.cornisa(lado)
        for p in self.puertas:
            self.habitacion(p)
        for w in self.ventanas:
            self.ventana(w)
        self.hacer_puente()
        for lado, ya in self.arcos:
            self.arco(lado, ya)
        self.topes()
        self.repartir_objetos()

    # objetos que se encuentran: por casas, de la entrada del valle hacia el fondo (curva de la zona 1)
    BOTIN = [
        # (casa nº en orden de y, [objetos])   ids de param/item_nam.prm
        (0, [151, 6, 6]),                # callejón: Cachiporra de madera, 2 Hierbas
        (1, [251, 6]),                   # callejón: Casco de cuero, Hierba
        (2, [221, 7]),                   # callejón: Escudo de madera, Jugo Herbal
        (3, [155, 276, 7]),              # sala grande: Espada Básica, Chaleco de retazos, Jugo Herbal
        (4, [6, 6, 223]),                # 2 Hierbas, Escudo de cuero
        (5, [301, 328, 12, 9]),          # Guantes de piel, Botas de piel, Hongos, Remedio
        (6, [71, 6, 7]),                 # Cristal de Fuego (primera magia), Hierba, Jugo Herbal
        (7, [9, 6]),                     # Remedio, Hierba (túnel del final)
    ]

    def repartir_objetos(self):
        casas = sorted(self.casas, key=lambda c: (c["p"]["y"] if c["p"]["lado"] == "W" else c["p"]["y"] + 0.1))
        self.objetos = []
        r = self.rng
        for idx, lista in self.BOTIN:
            if idx >= len(casas):
                continue
            c = casas[idx]
            s_, p = c["s"], c["p"]
            n = len(lista)
            for k, item in enumerate(lista):
                fx = 0.35 + 0.5 * (k % 2)
                fy = (k + 0.5) / n
                x = c["x_front"] + s_ * p["fondo"] * fx
                y = c["y0"] + 0.6 + (c["y1"] - c["y0"] - 1.2) * fy
                self.objetos.append((item, (x, y, c["z"])))
        # una hierba nada más empezar, en la cornisa
        a = self.intro[-1]
        self.objetos.append((6, (a[0] - 0.8, a[1] - 3.5, a[2])))
        # punto de guardado al fondo de la sala grande
        sala = [c for c in casas if c["p"]["tipo"] == "sala"]
        if sala:
            c = sala[0]
            self.guardado = (c["x_front"] + c["s"] * (c["p"]["fondo"] - 1.4), c["ym"], c["z"])
        else:
            self.guardado = None

    def hueco(self, lado, y, z):
        """¿La celda (columna y, fila z) es una abertura?"""
        for p in self.puertas:
            if p["lado"] == lado and abs(p["y"] - y) < 1e-6 and p["z"] - 1e-6 <= z < p["z"] + 2 * FILA - 1e-6:
                return "puerta"
        for w in self.ventanas:
            if w["lado"] == lado and not w["bajo_cornisa"] and abs(w["y"] - y) < 1e-6 and \
                    w["z"] - 1e-6 <= z < w["z"] + w["alto"] * FILA - 1e-6:
                return "ventana"
        return None

    def tex_fachada(self, lado, y, z):
        for p in self.puertas:
            if p["lado"] == lado and p["y"] - COL - 1e-6 <= y <= p["y"] + COL + 1e-6 and \
                    p["z"] - 1e-6 <= z <= p["z"] + 3 * FILA + 1e-6 and p["tipo"] != "tunel":
                return LADRILLO
        for w in self.ventanas:
            if w["lado"] == lado and not w["bajo_cornisa"] and abs(w["y"] - y) < 1e-6 and \
                    (abs(z - (w["z"] - FILA)) < 1e-6 or abs(z - (w["z"] + w["alto"] * FILA)) < 1e-6):
                return LADRILLO_OSC
        return None

    def muro(self, lado):
        cols = self.columnas()
        filas = self.filas()
        L = self.luz
        V = {}
        for y in cols:
            for z in filas:
                V[(y, z)] = self.punto_muro(lado, y, z)

        def normal(y, z, iy, iz):
            ya, yb = cols[max(0, iy - 1)], cols[min(len(cols) - 1, iy + 1)]
            za, zb = filas[max(0, iz - 1)], filas[min(len(filas) - 1, iz + 1)]
            t1 = sub(V[(yb, z)], V[(ya, z)])
            t2 = sub(V[(y, zb)], V[(y, za)])
            n = norm(cross(t1, t2))
            want = -self.interior_dir(lado)
            return n if n[0] * want >= 0 else mul(n, -1)

        # oclusión: un vértice más hundido que sus vecinos (grieta) se oscurece, uno saliente se aclara;
        # y la pared se oscurece al llegar al suelo de la cornisa
        s_in = self.interior_dir(lado)
        AO = {}
        for iy, y in enumerate(cols):
            zc = self.z_camino(lado, y)
            for iz, z in enumerate(filas):
                nb = [V[(cols[j], z)][0] for j in (iy - 1, iy + 1) if 0 <= j < len(cols)]
                nb += [V[(y, filas[j])][0] for j in (iz - 1, iz + 1) if 0 <= j < len(filas)]
                hund = s_in * (V[(y, z)][0] - sum(nb) / len(nb))
                f = clamp(1.0 - 0.75 * hund, 0.5, 1.22)
                if zc is not None and zc - 0.01 <= z < zc + 1.8:
                    f *= 0.45 + 0.55 * (z - zc) / 1.8
                AO[(y, z)] = f
        self._ao = AO
        N = {}
        for iy, y in enumerate(cols):
            for iz, z in enumerate(filas):
                N[(y, z)] = normal(y, z, iy, iz)
        for iz in range(len(filas) - 1):
            z0, z1 = filas[iz], filas[iz + 1]
            run = []
            run_tex = None
            for iy in range(len(cols) - 1):
                y0, y1 = cols[iy], cols[iy + 1]
                zc = [self.z_camino(lado, y0), self.z_camino(lado, y1)]
                # oculto detrás de la cornisa (dentro de la roca)
                tapado = all(c is not None for c in zc) and z1 <= min(zc) + 1e-6
                h = self.hueco(lado, y0, z0)
                banda, _ = self.luz.estrato(y0 + COL / 2, (z0 + z1) / 2)
                roca = ROCA if (banda + (1 if self.ruido.v(banda * 3.1, y0 * 0.01, 5) > 0.8 else 0)) % 2 == 0 else ROCA_VERDE
                tex = self.tex_fachada(lado, y0, z0) or roca
                keep = not tapado and h is None
                if keep and run and tex == run_tex:
                    run.append(iy)
                else:
                    if run:
                        self._emit_fila(lado, cols, run, z0, z1, V, N, run_tex)
                    run = [iy] if keep else []
                    run_tex = tex
                # colisión del muro cerca del camino
                if keep:
                    zz = [c for c in zc if c is not None]
                    if zz and min(zz) - 1.0 <= z0 <= max(zz) + 4.5:
                        ch = self.chunk(lado, (y0 + y1) / 2)
                        self.geo.cquad(ch, "wall", V[(y0, z0)], V[(y1, z0)], V[(y1, z1)], V[(y0, z1)])
            if run:
                self._emit_fila(lado, cols, run, z0, z1, V, N, run_tex)

    def _emit_fila(self, lado, cols, run, z0, z1, V, N, tex):
        """Una fila de celdas consecutivas del muro -> tiras (pares abajo/arriba a lo largo de Y)."""
        L = self.luz
        esc = 5.0 if tex in (ROCA, ROCA_VERDE) else 3.0
        grupos = collections.defaultdict(list)
        for iy in run:
            grupos[self.chunk(lado, cols[iy] + COL / 2)].append(iy)
        for ch, idxs in grupos.items():
            tramo = [idxs[0]]
            for iy in idxs[1:] + [None]:
                if iy is not None and iy == tramo[-1] + 1:
                    tramo.append(iy)
                    continue
                seq = []
                for k in [tramo[0]] + [t + 1 for t in tramo]:
                    yy = cols[k]
                    for z in (z0, z1):
                        p = V[(yy, z)]
                        n = N[(yy, z)]
                        ao = self._ao.get((yy, z), 1.0)
                        seq.append((p, (yy / esc, -z / esc), mul(L.roca(p, n), ao), n))
                self.geo.strip(ch, tex, seq)
                if iy is not None:
                    tramo = [iy]

    def cornisa(self, lado):
        c = self.cornisas[lado]
        s = self.interior_dir(lado)
        L = self.luz
        filas = self.filas()
        y = c["y0"]
        paso = COL
        ys = []
        while y <= c["y1"] + 1e-6:
            ys.append(round(y, 4))
            y += paso
        # añadir puntos intermedios en rampas para los escalones
        for i in range(len(ys) - 1):
            y0, y1 = ys[i], ys[i + 1]
            ym = (y0 + y1) / 2
            z0, z1 = self.z_camino(lado, y0), self.z_camino(lado, y1)
            rampa = self.es_rampa(lado, ym) or abs(z1 - z0) > 1e-6
            ch = self.chunk(lado, ym)
            xi0 = self.borde_suelo(lado, y0, z0, ym)
            xi1 = self.borde_suelo(lado, y1, z1, ym)
            xo0 = self.muro_x(lado, y0, z0) - s * self.ancho(lado, y0)
            xo1 = self.muro_x(lado, y1, z1) - s * self.ancho(lado, y1)
            a, b = (xi0, y0, z0), (xi1, y1, z1)
            cc, d = (xo1, y1, z1), (xo0, y0, z0)
            up = (0.0, 0.0, 1.0)
            if rampa:
                # escalones visuales; colisión: rampa lisa
                pasos = max(1, int(round(abs(z1 - z0) / 0.3)))
                for k in range(pasos):
                    t0, t1 = k / pasos, (k + 1) / pasos
                    ya, yb = y0 + (y1 - y0) * t0, y0 + (y1 - y0) * t1
                    za = z0 + (z1 - z0) * t0
                    zb = z0 + (z1 - z0) * t1
                    zt = zb if z1 > z0 else za   # huella a la altura del escalón
                    xa_i, xb_i = xi0 + (xi1 - xi0) * t0, xi0 + (xi1 - xi0) * t1
                    xa_o, xb_o = xo0 + (xo1 - xo0) * t0, xo0 + (xo1 - xo0) * t1
                    col = L.roca((xa_o, ya, zt), up)
                    self.geo.quad(ch, LOSAS, (xa_i, ya, zt), (xb_i, yb, zt), (xb_o, yb, zt), (xa_o, ya, zt),
                                  (0, ya / 3), (0, yb / 3), (1.25, yb / 3), (1.25, ya / 3), col, col, col, col, up)
                    # contrahuella
                    zr0, zr1 = (za, zb) if z1 > z0 else (zb, za)
                    yr = ya if z1 > z0 else yb
                    xr_i = xa_i if z1 > z0 else xb_i
                    xr_o = xa_o if z1 > z0 else xb_o
                    cr = mul(col, 0.8)
                    self.geo.quad(ch, LOSAS, (xr_i, yr, zr0), (xr_o, yr, zr0), (xr_o, yr, zr1), (xr_i, yr, zr1),
                                  (0, 0), (1.25, 0), (1.25, 0.1), (0, 0.1), cr, cr, cr, cr, (0, -1, 0))
                self.geo.cquad(ch, "floor", a, b, cc, d)
            else:
                ca, cb = L.roca(a, up), L.roca(b, up)
                cd_, cc_ = L.roca(d, up), L.roca(cc, up)
                ca, cb = mul(ca, 0.5), mul(cb, 0.5)   # rincón contra el muro, más oscuro
                suelo = self.suelo_tex(lado, ym)
                if suelo == LOSAS:
                    ua, ub = abs(a[0] - d[0]) / 3.0, abs(b[0] - cc[0]) / 3.0
                    uvs = ((0, y0 / 3), (0, y1 / 3), (ub, y1 / 3), (ua, y0 / 3))
                else:   # tramos de roca viva o de cascotes: el suelo no siempre es de losas
                    e_ = 4.0 if suelo == ROCA else 2.2
                    uvs = tuple((q[0] / e_, q[1] / e_) for q in (a, b, cc, d))
                    k_ = 0.82 if suelo == ROCA else 0.9
                    ca, cb, cc_, cd_ = (mul(c_, k_) for c_ in (ca, cb, cc_, cd_))
                self.geo.quad(ch, suelo, a, b, cc, d, *uvs, ca, cb, cc_, cd_, up)
                self.geo.cquad(ch, "floor", a, b, cc, d)
            # pretil (bordillo) y barandilla invisible
            enpuente = self.puente and lado in "WE" and self.puente[0] - 0.01 <= ym <= self.puente[1] + 0.01
            bajo_arco = any(la == lado and abs(ym - ya) < 2.0 for la, ya in self.arcos)
            roto = not rampa and self.suelo_tex(lado, ym) == ROCA   # pretil derrumbado (la barandilla invisible sigue)
            if bajo_arco or roto:
                p0, p1 = (xo0, y0, z0), (xo1, y1, z1)
                self.geo.cquad(ch, "wall", p0, p1, add(p1, (0, 0, 2.2)), add(p0, (0, 0, 2.2)))
            if not enpuente and not bajo_arco and not roto:
                hp = 0.55
                wp = 0.35
                p0 = (xo0, y0, z0)
                p1 = (xo1, y1, z1)
                p0i = (xo0 + s * wp, y0, z0)
                p1i = (xo1 + s * wp, y1, z1)
                cl = L.roca(p0, up)
                for (q0, q1, uvz) in ((p0, p1, 0.0), (p1i, p0i, 0.0)):
                    self.geo.quad(ch, LADRILLO_OSC, q0, q1, add(q1, (0, 0, hp)), add(q0, (0, 0, hp)),
                                  (y0 / 3, 0.2), (y1 / 3, 0.2), (y1 / 3, 0), (y0 / 3, 0), cl, cl, cl, cl)
                ct = mul(cl, 1.1)
                self.geo.quad(ch, VIGA, add(p0, (0, 0, hp)), add(p1, (0, 0, hp)), add(p1i, (0, 0, hp)),
                              add(p0i, (0, 0, hp)), (y0 / 4, 0), (y1 / 4, 0), (y1 / 4, 1), (y0 / 4, 1), ct, ct, ct, ct, up)
                self.geo.cquad(ch, "wall", p0, p1, add(p1, (0, 0, 2.2)), add(p0, (0, 0, 2.2)))
            # moldura bajo el borde de la cornisa
            if not enpuente:
                tr = 0.09
                q = [(xo0 - s * tr, y0, z0 - 0.65), (xo1 - s * tr, y1, z1 - 0.65), (xo1 - s * tr, y1, z1 - 0.02),
                     (xo0 - s * tr, y0, z0 - 0.02)]
                nrm = (-s, 0.0, 0.0)
                cq = [mul(L.roca(v, nrm), 0.95) for v in q]
                self.geo.quad(ch, VIGA, *q, (y0 / 4, 1), (y1 / 4, 1), (y1 / 4, 0), (y0 / 4, 0), *cq, nrm)
                self.geo.quad(ch, VIGA, (xo0, y0, z0 - 0.65), (xo1, y1, z1 - 0.65), q[1], q[0],
                              (y0 / 4, 0), (y1 / 4, 0), (y1 / 4, 0.15), (y0 / 4, 0.15),
                              *[mul(c_, 0.6) for c_ in cq[:2]], *[mul(c_, 0.6) for c_ in cq[:2]], (0, 0, -1))
            # cara exterior de la cornisa: cae hasta perderse
            ztop = min(z0, z1)
            niveles = [z for z in filas if z < ztop - 0.3] + [None]
            ladof = (ROCA if self.ruido.v(y0 * 0.05, 3.3, 5) > 0.4 else ROCA_VERDE)
            n = (-s, 0.0, 0.0)
            pares = []
            for z in niveles:
                za_, zb_ = (z0, z1) if z is None else (z, z)
                zr = ztop if z is None else z
                pa = (xo0 - s * self.cara_d(lado, y0, zr), y0, za_)
                pb = (xo1 - s * self.cara_d(lado, y1, zr), y1, zb_)
                pares.append((zr, (pa, (y0 / 5, -za_ / 5), L.roca(pa, n), n), (pb, (y1 / 5, -zb_ / 5), L.roca(pb, n), n)))
            run = []
            for k, (zr, va, vb) in enumerate(pares):
                run.append(va)
                run.append(vb)
                hole = any(w["lado"] == lado and w["bajo_cornisa"] and abs(w["y"] - y0) < 1e-6 and
                           w["z"] - 1e-6 <= zr < w["z"] + w["alto"] * FILA - 1e-6 for w in self.ventanas)
                if hole:
                    self.geo.strip(ch, ladof, run)
                    run = []
            self.geo.strip(ch, ladof, run)

    def suelo_tex(self, lado, ym):
        """Material del suelo de la cornisa en ese tramo: losas casi siempre, a ratos roca o cascotes."""
        if self.es_puerta(lado, ym) or self.es_rampa(lado, ym):
            return LOSAS
        v = self.ruido.v(ym * 0.23, 3.3 if lado == "W" else 8.1, 41)
        if v > 0.68:
            return ROCA_PEQ
        if v < 0.2:
            return ROCA
        return LOSAS

    def es_puerta(self, lado, ym):
        return any(p["lado"] == lado and p["y"] - 1e-6 <= ym <= p["y"] + COL + 1e-6 for p in self.puertas)

    def borde_suelo(self, lado, y, z, ym):
        """x del borde interior del suelo de la cornisa en y: un poco dentro de la roca, siguiendo la
        pared que hay de verdad entre las dos filas que rodean la altura del suelo. En una puerta, en la
        fachada exacta (allí empieza el umbral de la casa: así no hay dos suelos en el mismo plano)."""
        s = self.interior_dir(lado)
        if self.es_puerta(lado, ym):
            return self.punto_muro(lado, y, z)[0]
        filas = self.filas()
        lo = max([f for f in filas if f <= z + 1e-6] or [z])
        hi = min([f for f in filas if f > z + 1e-6] or [z])
        xs = [self.punto_muro(lado, y, lo)[0], self.punto_muro(lado, y, hi)[0], self.punto_muro(lado, y, z)[0]]
        deep = min(xs) if s < 0 else max(xs)
        return deep + s * 0.35

    def cara_d(self, lado, y, z):
        """Rugosidad de la cara exterior de la cornisa (hacia fuera positivo)."""
        m = 1.0
        for w in self.ventanas:
            if w["lado"] == lado and w["bajo_cornisa"]:
                dy = max(w["y"] - y, 0.0, y - (w["y"] + COL))
                dz = max(w["z"] - z, 0.0, z - (w["z"] + w["alto"] * FILA))
                m = min(m, clamp(max(dy, dz) / 1.6, 0, 1))
        zc = self.z_camino(lado, y)
        if zc is not None and z > zc - 1.5:
            m = min(m, 0.2)
        return self.ruido.fbm(y * 0.12, z * 0.12, 23 if lado == "W" else 29) * 1.1 * m

    # ---- habitaciones excavadas ----
    def caja(self, ch, lado, x_front, y0, y1, z0, z1, fondo, tex_par, tex_suelo, tex_techo, luzf, hueco=None,
             coll=False, molduras=True):
        """Caja de habitación dentro de la roca. hueco = (ya, yb, za, zb) en la pared frontal."""
        s = self.interior_dir(lado)
        xb = x_front + s * fondo
        luz_base = luzf

        def luzf(p, _b=luz_base):            # paredes: oscuras al pie y bajo el techo, y en las esquinas
            k = 1.0
            if abs(p[2] - z0) < 1e-4:
                k *= 0.55
            elif abs(p[2] - z1) < 1e-4:
                k *= 0.75
            if abs(p[1] - y0) < 1e-4 or abs(p[1] - y1) < 1e-4:
                k *= 0.85
            return mul(_b(p), k)
        up = (0, 0, 1)
        P = lambda x, y, z: (x, y, z)
        h = z1 - z0
        vt = (1.0 if molduras else h / 3.0)
        # suelo
        a, b, c, d = P(x_front, y0, z0), P(x_front, y1, z0), P(xb, y1, z0), P(xb, y0, z0)
        self.geo.quad(ch, tex_suelo, a, b, c, d, (0, y0 / 3), (0, y1 / 3), (fondo / 3, y1 / 3), (fondo / 3, y0 / 3),
                      *[mul(luz_base(v), 0.85) for v in (a, b, c, d)], up)
        # techo
        a2, b2, c2, d2 = P(x_front, y0, z1), P(xb, y0, z1), P(xb, y1, z1), P(x_front, y1, z1)
        self.geo.quad(ch, tex_techo, a2, b2, c2, d2, (0, 0), (fondo / 4, 0), (fondo / 4, (y1 - y0) / 4), (0, (y1 - y0) / 4),
                      mul(luzf(a2), 0.7), mul(luzf(b2), 0.7), mul(luzf(c2), 0.7), mul(luzf(d2), 0.7), (0, 0, -1))
        # fondo
        q = [P(xb, y0, z0), P(xb, y1, z0), P(xb, y1, z1), P(xb, y0, z1)]
        self.geo.quad(ch, tex_par, *q, (0, vt), ((y1 - y0) / 3.6, vt), ((y1 - y0) / 3.6, 0), (0, 0),
                      *[luzf(p) for p in q], (-s, 0, 0))
        # laterales
        for (yy, sg) in ((y0, 1), (y1, -1)):
            q = [P(x_front, yy, z0), P(xb, yy, z0), P(xb, yy, z1), P(x_front, yy, z1)]
            self.geo.quad(ch, tex_par, *q, (0, vt), (fondo / 3.6, vt), (fondo / 3.6, 0), (0, 0),
                          *[luzf(p) for p in q], (0, sg, 0))
        # pared frontal interior con hueco
        if hueco:
            ya, yb, za, zb = hueco
            for (q, uv) in (
                    ([P(x_front, y0, z0), P(x_front, ya, z0), P(x_front, ya, z1), P(x_front, y0, z1)], None),
                    ([P(x_front, yb, z0), P(x_front, y1, z0), P(x_front, y1, z1), P(x_front, yb, z1)], None),
                    ([P(x_front, ya, zb), P(x_front, yb, zb), P(x_front, yb, z1), P(x_front, ya, z1)], None),
                    ([P(x_front, ya, z0), P(x_front, yb, z0), P(x_front, yb, za), P(x_front, ya, za)], None)):
                if abs(q[0][1] - q[1][1]) < 1e-6 or abs(q[0][2] - q[3][2]) < 1e-6:
                    continue
                uvs = [((p[1] - y0) / 3.6, vt * (z1 - p[2]) / h) for p in q]
                self.geo.quad(ch, tex_par, *q, *uvs, *[luzf(p) for p in q], (s * -1, 0, 0))
        if coll:
            self.geo.cquad(ch, "floor", P(x_front, y0, z0), P(x_front, y1, z0), P(xb, y1, z0), P(xb, y0, z0))
            self.geo.cquad(ch, "wall", P(xb, y0, z0), P(xb, y1, z0), P(xb, y1, z1), P(xb, y0, z1))
            self.geo.cquad(ch, "wall", P(x_front, y0, z0), P(xb, y0, z0), P(xb, y0, z1), P(x_front, y0, z1))
            self.geo.cquad(ch, "wall", P(x_front, y1, z0), P(xb, y1, z0), P(xb, y1, z1), P(x_front, y1, z1))
            if hueco:
                ya, yb, za, zb = hueco
                self.geo.cquad(ch, "wall", P(x_front, y0, z0), P(x_front, ya, z0), P(x_front, ya, z1), P(x_front, y0, z1))
                self.geo.cquad(ch, "wall", P(x_front, yb, z0), P(x_front, y1, z0), P(x_front, y1, z1), P(x_front, yb, z1))

    def revestir(self, ch, lado, corners, x_front, tex, luzf, saltar=()):
        """Jambas del hueco: une cada borde del hueco en la fachada con el plano de la pared interior
        (x_front exacto, así no quedan rendijas aunque la fachada no sea plana). saltar: bordes sin jamba."""
        n = len(corners)
        for i in range(n):
            if i in saltar:
                continue
            a = corners[i]
            b = corners[(i + 1) % n]
            a2 = (x_front, a[1], a[2])
            b2 = (x_front, b[1], b[2])
            prof = abs(x_front - a[0])
            q = [a, b, b2, a2]
            self.geo.quad(ch, tex, *q, (0, 0), (1, 0), (1, prof / 2), (0, prof / 2), *[mul(luzf(p), 0.8) for p in q])

    def habitacion(self, p):
        lado = p["lado"]
        s = self.interior_dir(lado)
        y_door = p["y"]
        z0 = p["z"]
        zt = z0 + 2 * FILA
        ch = self.chunk(lado, y_door + COL / 2)
        # esquinas del hueco sobre la fachada (roca aplanada ahí)
        c = [self.punto_muro(lado, y_door, z0), self.punto_muro(lado, y_door + COL, z0),
             self.punto_muro(lado, y_door + COL, zt), self.punto_muro(lado, y_door, zt)]
        grosor = 0.6
        ancho = p["ancho"] * COL
        ym = y_door + COL / 2
        y0, y1 = ym - ancho / 2, ym + ancho / 2
        alto = p["alto"]
        x_front = self.fondo_roca(lado, y0, y1, z0, z0 + alto, c) + s * grosor
        centro = (x_front + s * p["fondo"] * 0.5, ym, z0 + alto * 0.7)
        if p["tipo"] == "tunel":
            luzf = lambda q: mul(self.luz.calida(q, (x_front, ym, z0 + 1.5), 14.0, 0.5, 0.18), 0.85)
            tp, ts, tt = ROCA_PEQ, LOSAS, ROCA_PEQ
            molduras = False
        else:
            luzf = lambda q: self.luz.calida(q, centro, max(6.0, p["fondo"]), 0.85, 0.30)
            tp, ts, tt = (RELIEVE if p["tipo"] == "sala" else YESO), LOSAS, ROCA_PEQ
            molduras = p["tipo"] != "sala"
        # suelo del umbral (entre la fachada y la habitación)
        up = (0, 0, 1)
        a, b = c[0], c[1]
        a2 = (x_front, y_door, z0)
        b2 = (x_front, y_door + COL, z0)
        cl = luzf(a2)
        self.geo.quad(ch, LOSAS, a, b, b2, a2, (0, 0), (1, 0), (1, 0.3), (0, 0.3), cl, cl, cl, cl, up)
        self.geo.cquad(ch, "floor", a, b, b2, a2)
        self.revestir(ch, lado, c, x_front, LADRILLO, luzf, saltar=(0,))   # el borde de abajo es el umbral
        self.geo.cquad(ch, "wall", c[0], c[3], (x_front, y_door, zt), (x_front, y_door, z0))
        self.geo.cquad(ch, "wall", c[1], c[2], (x_front, y_door + COL, zt), (x_front, y_door + COL, z0))
        self.caja(ch, lado, x_front, y0, y1, z0, z0 + alto, p["fondo"], tp, ts, tt, luzf,
                  hueco=(y_door, y_door + COL, z0, zt), coll=True, molduras=molduras)
        if p["tipo"] != "tunel":
            # dintel de piedra labrada sobre la puerta
            sal = 0.18
            x_fuera = max(c[2][0], c[3][0]) if s < 0 else min(c[2][0], c[3][0])   # la esquina más saliente
            xa = x_fuera - s * sal
            ya_, yb_ = y_door - 0.6, y_door + COL + 0.6
            q = [(xa, ya_, zt), (xa, yb_, zt), (xa, yb_, zt + 0.6), (xa, ya_, zt + 0.6)]
            nrm = (-s, 0.0, 0.0)
            cq = [self.luz.roca(v, nrm) for v in q]
            self.geo.quad(ch, FRISO, *q, (0, 1), (1.5, 1), (1.5, 0), (0, 0), *cq, nrm)
            base = [(x_fuera, ya_, zt), (x_fuera, yb_, zt)]
            self.geo.quad(ch, FRISO, base[0], base[1], q[1], q[0], (0, 0.9), (1.5, 0.9), (1.5, 1), (0, 1),
                          *[mul(cq[0], 0.5)] * 4, (0, 0, -1))
            top = [(x_fuera, ya_, zt + 0.6), (x_fuera, yb_, zt + 0.6)]
            self.geo.quad(ch, FRISO, q[3], q[2], top[1], top[0], (0, 0), (1.5, 0), (1.5, 0.1), (0, 0.1),
                          *[mul(cq[0], 1.1)] * 4, (0, 0, 1))
        # objeto dentro (posiciones para los items de 099)
        self.items_pos.append((x_front + s * p["fondo"] * 0.7, ym, z0))
        self.casas.append({"p": p, "s": s, "x_front": x_front, "y0": y0, "y1": y1, "ym": ym, "z": z0})

    def fondo_roca(self, lado, y0, y1, z0, z1, extra=()):
        """El punto más hundido de la fachada delante de una habitación: la caja empieza detrás de él,
        así no asoma por la roca."""
        s = self.interior_dir(lado)
        xs = [q[0] for q in extra]
        ny = max(2, int((y1 - y0) / 0.5))
        nz = max(2, int((z1 - z0) / 0.5))
        for i in range(ny + 1):
            for j in range(nz + 1):
                xs.append(self.punto_muro(lado, y0 + (y1 - y0) * i / ny, z0 + (z1 - z0) * j / nz)[0])
        return min(xs) if s < 0 else max(xs)

    def ventana(self, w):
        lado = w["lado"]
        s = self.interior_dir(lado)
        y0, y1 = w["y"], w["y"] + COL
        za, zb = w["z"], w["z"] + w["alto"] * FILA
        ch = self.chunk(lado, (y0 + y1) / 2)
        if w["bajo_cornisa"]:
            xo = lambda y: self.muro_x(lado, y, self.z_camino(lado, y) or 0) - s * self.ancho(lado, y)
            c = [(xo(y0) - s * self.cara_d(lado, y0, za), y0, za), (xo(y1) - s * self.cara_d(lado, y1, za), y1, za),
                 (xo(y1) - s * self.cara_d(lado, y1, zb), y1, zb), (xo(y0) - s * self.cara_d(lado, y0, zb), y0, zb)]
        else:
            c = [self.punto_muro(lado, y0, za), self.punto_muro(lado, y1, za),
                 self.punto_muro(lado, y1, zb), self.punto_muro(lado, y0, zb)]
        grosor = 0.45
        if w["bajo_cornisa"]:
            x_front = (min(q[0] for q in c) if s < 0 else max(q[0] for q in c)) + s * (grosor + 1.2)
        else:
            x_front = self.fondo_roca(lado, y0 - 0.6, y1 + 0.6, za - 0.3, zb + 0.5, c) + s * grosor
        cen = (x_front + s * w["fondo"] * 0.5, (y0 + y1) / 2, (za + zb) / 2)
        if w["luz"]:
            luzf = lambda q: self.luz.calida(q, cen, 3.2, 1.05, 0.30)
        else:
            luzf = lambda q: mul(self.luz.roca(q, (0, 0, 1)), 0.25)
        self.revestir(ch, lado, c, x_front, LADRILLO_OSC, luzf)
        m = 0.6
        self.caja(ch, lado, x_front, y0 - m, y1 + m, za - 0.3, zb + 0.5, w["fondo"],
                  YESO if w["luz"] else ROCA_PEQ, LOSAS, ROCA_PEQ, luzf, hueco=(y0, y1, za, zb))

    # ---- puente ----
    # contorno del arco en (u, h): u = metros hacia el vacío desde el muro, h = altura sobre el camino.
    # W = ancho del camino. Hueco (por donde pasas) y silueta exterior, con el mismo nº de puntos: la cara
    # del arco es la banda entre los dos. El pie de fuera baja por el acantilado hasta perderse.
    ARCO_HUECO = [(-0.4, -0.3), (-0.35, 1.6), (-0.15, 2.7), (0.35, 3.45), ("m", 3.85), ("W-0.6", 3.55),
                  ("W-0.05", 2.8), ("W+0.05", 1.4), ("W-0.15", -0.9)]
    ARCO_FUERA = [(-2.2, 4.2), (-1.6, 6.8), (-0.4, 8.4), (0.8, 9.3), ("m", 8.7), ("W+0.9", 8.3),
                  ("W+2.2", 6.4), ("W+2.6", 2.2), ("W+2.1", -15.0)]

    def arco(self, lado, yc, grosor=3.4):
        """Arco natural de roca (boceto del usuario): una masa de roca maciza que sale del muro, pasa por
        encima del camino y baja por el borde del acantilado como un pilar grueso. Se pasa por debajo."""
        s = self.interior_dir(lado)
        L = self.luz
        Rn = self.ruido
        ch = self.chunk(lado, yc)

        def val(v, W):
            if isinstance(v, str):
                return W * 0.5 if v == "m" else W + float(v[1:])
            return v

        def suave(pts, k=3):
            """Catmull-Rom entre los puntos de control: k puntos por tramo."""
            out = []
            for i in range(len(pts) - 1):
                p0, p1, p2, p3 = pts[max(0, i - 1)], pts[i], pts[i + 1], pts[min(len(pts) - 1, i + 2)]
                for j in range(k):
                    t = j / k
                    t2, t3 = t * t, t * t * t
                    out.append(tuple(0.5 * (2 * p1[c] + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t2
                                            + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t3) for c in range(2)))
            out.append(pts[-1])
            return out

        def contorno(tabla, y, amp, semilla):
            z0 = self.z_camino(lado, y)
            W = self.ancho(lado, y)
            xw = self.muro_x(lado, y, z0)
            pts = suave([(val(u, W), h) for u, h in tabla])
            out = []
            for i, (u, h) in enumerate(pts):
                n1 = Rn.fbm(i * 0.37 + y * 0.21, h * 0.25, semilla, 3)
                n2 = Rn.fbm(i * 0.41 + 3.1, y * 0.19 + h * 0.21, semilla + 1, 3)
                fin = i in (0, len(pts) - 1)
                u += amp * n1 * (0.3 if fin else 1.0)
                h += amp * 0.8 * n2 * (0.3 if fin else 1.0)
                out.append((xw - s * u, y, z0 + h))
            return out
        ya, yb = yc - grosor / 2, yc + grosor / 2
        caras = {}
        for nombre, y, sgn in (("frente", ya, -1.0), ("fondo", yb, 1.0)):
            hu = contorno(self.ARCO_HUECO, y, 0.12, 71)
            fu = contorno(self.ARCO_FUERA, y, 0.8, 73)
            # la cara no es plana: abombada hacia fuera en el centro y más gruesa abajo
            def bulto(p, k):
                return (p[0], p[1] + sgn * (0.25 + 0.45 * Rn.fbm(p[0] * 0.5, p[2] * 0.4, k, 3)
                                            + 0.04 * max(0.0, -p[2])), p[2])
            fu = [bulto(p, 75 if sgn < 0 else 77) for p in fu]
            caras[nombre] = (hu, fu)
            n = (0.0, sgn, 0.0)
            # cara en dos bandas: junto al hueco oscura (sombra de la roca), hacia fuera más clara
            mid = [tuple(a_ + (b_ - a_) * 0.35 for a_, b_ in zip(h_, f_)) for h_, f_ in zip(hu, fu)]
            for banda, (P, Q, k0, k1) in enumerate(((hu, mid, 0.5, 0.82), (mid, fu, 0.82, 1.05))):
                for i in range(len(P) - 1):
                    q = [P[i], P[i + 1], Q[i + 1], Q[i]]
                    ks = [k0, k0, k1, k1]
                    if sgn > 0:
                        q = [q[1], q[0], q[3], q[2]]
                        ks = [ks[1], ks[0], ks[3], ks[2]]
                    cols = [mul(L.roca(p, n), k_) for p, k_ in zip(q, ks)]
                    tex = ROCA_VERDE if banda == 1 else ROCA
                    self.geo.quad(ch, tex, *q, *[(p[0] / 5, -p[2] / 5) for p in q], *cols, n)
        # superficies que unen las dos caras: el hueco (techo y jambas) y la piel exterior
        for clave, oscuro, tex in ((0, 0.62, ROCA_PEQ), (1, 1.0, ROCA)):
            A, B = caras["frente"][clave], caras["fondo"][clave]
            largo = 0.0
            for i in range(len(A) - 1):
                a, b, c, d = A[i], A[i + 1], B[i + 1], B[i]
                if clave == 1:
                    a, b, c, d = b, a, d, c
                du = math.dist(A[i], A[i + 1])
                e = sub(A[i + 1], A[i])
                nrm = norm(cross(e, (0.0, 1.0, 0.0)))
                if clave == 0:
                    nrm = mul(nrm, -1.0)
                cols = [mul(L.roca(p, nrm, 0.35 if clave == 0 else 0.0), oscuro) for p in (a, b, c, d)]
                u0, u1 = largo / 5, (largo + du) / 5
                if clave == 1:
                    u0, u1 = u1, u0
                self.geo.quad(ch, tex, a, b, c, d, (u0, a[1] / 5), (u1, b[1] / 5), (u1, c[1] / 5), (u0, d[1] / 5),
                              *cols, nrm)
                largo += du
        # colisión: la jamba de fuera (el pilar) no se atraviesa
        A, B = caras["frente"][0], caras["fondo"][0]
        for i in range(len(A) - 1):
            zc = self.z_camino(lado, yc)
            if A[i][2] < zc + 3.2 and A[i + 1][2] < zc + 3.2 and -s * (A[i][0] - self.muro_x(lado, ya, zc)) > 1.0:
                self.geo.cquad(ch, "wall", A[i], A[i + 1], B[i + 1], B[i])

    def hacer_puente(self):
        ya, yb, z = self.puente
        xw0 = self.muro_x("W", ya, z) + self.ancho("W", ya) - 0.2
        xw1 = self.muro_x("W", yb, z) + self.ancho("W", yb) - 0.2
        xe0 = self.muro_x("E", ya, z) - self.ancho("E", ya) + 0.2
        xe1 = self.muro_x("E", yb, z) - self.ancho("E", yb) + 0.2
        L = self.luz
        up = (0, 0, 1)
        n = 8
        grosor = 0.9
        for i in range(n):
            t0, t1 = i / n, (i + 1) / n
            x00, x01 = xw0 + (xe0 - xw0) * t0, xw0 + (xe0 - xw0) * t1
            x10, x11 = xw1 + (xe1 - xw1) * t0, xw1 + (xe1 - xw1) * t1
            # ligera curva hacia abajo (catenaria)
            zz0 = z - 0.35 * math.sin(math.pi * t0)
            zz1 = z - 0.35 * math.sin(math.pi * t1)
            xm = (x00 + x01) / 2
            ch = self.chunk("W" if xm < 0 else "E", (ya + yb) / 2)
            a, b, c, d = (x00, ya, zz0), (x01, ya, zz1), (x11, yb, zz1), (x10, yb, zz0)
            col = L.roca(a, up)
            self.geo.quad(ch, LOSAS, a, b, c, d, (x00 / 3, 0), (x01 / 3, 0), (x01 / 3, 1.6), (x00 / 3, 1.6),
                          col, col, col, col, up)
            self.geo.cquad(ch, "floor", a, b, c, d)
            bajo = [(p[0], p[1], p[2] - grosor) for p in (a, b, c, d)]
            cb = mul(col, 0.55)
            self.geo.quad(ch, LADRILLO_OSC, bajo[1], bajo[0], bajo[3], bajo[2], (0, 0), (1, 0), (1, 1), (0, 1),
                          cb, cb, cb, cb, (0, 0, -1))
            for (p, q, pb, qb) in ((a, b, bajo[0], bajo[1]), (c, d, bajo[2], bajo[3])):
                self.geo.quad(ch, LADRILLO_OSC, pb, qb, q, p, (p[0] / 3, 0.3), (q[0] / 3, 0.3), (q[0] / 3, 0), (p[0] / 3, 0),
                              cb, cb, col, col)
                # pretil del puente
                hp = 0.7
                self.geo.quad(ch, LADRILLO_OSC, p, q, add(q, (0, 0, hp)), add(p, (0, 0, hp)),
                              (p[0] / 3, 0.25), (q[0] / 3, 0.25), (q[0] / 3, 0), (p[0] / 3, 0), col, col, col, col)
                self.geo.cquad(ch, "wall", p, q, add(q, (0, 0, 2.2)), add(p, (0, 0, 2.2)))

    def topes(self):
        """Contrafuertes de roca donde acaban las cornisas."""
        for lado, c in self.cornisas.items():
            s = self.interior_dir(lado)
            for (y, dy) in ((c["y0"], -1.0), (c["y1"], 1.0)):
                z = self.z_camino(lado, y)
                ch = self.chunk(lado, y)
                xi = self.muro_x(lado, y, z) + s * 0.5
                xo = self.muro_x(lado, y, z) - s * (self.ancho(lado, y) + 2.0)
                y2 = y + dy * 3.0
                top = z + 16.0
                bot = -230.0
                L = self.luz
                # cara frontal (hacia el camino) y cara exterior, en tramos de 25 m de alto
                zs = [bot]
                while zs[-1] < top:
                    zs.append(min(top, zs[-1] + 25.0))
                for (pa, pb, n) in (((xi, y), (xo, y), (0, -dy, 0)), ((xo, y), (xo, y2), (-s, 0, 0))):
                    for za_, zb_ in zip(zs, zs[1:]):
                        q = [(pa[0], pa[1], za_), (pb[0], pb[1], za_), (pb[0], pb[1], zb_), (pa[0], pa[1], zb_)]
                        w_ = math.hypot(pb[0] - pa[0], pb[1] - pa[1]) / 5
                        cols = [L.roca(p, n) for p in q]
                        self.geo.quad(ch, ROCA, *q, (0, 0), (w_, 0), (w_, -(zb_ - za_) / 5), (0, -(zb_ - za_) / 5), *cols, n)
                self.geo.cquad(ch, "wall", (xi, y, z - 1), (xo, y, z - 1), (xo, y, z + 4), (xi, y, z + 4))


# ======================= Revisión automática =======================
def _clip(poly, a, b):
    """Sutherland-Hodgman: recorta el polígono por el semiplano a la izquierda de a->b."""
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        sp = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        sq = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
        if sp >= 0:
            out.append(p)
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq)
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def _area(poly):
    return 0.5 * abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                         for i in range(len(poly))))


def _ccw(poly):
    a = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
            for i in range(len(poly)))
    return poly if a > 0 else poly[::-1]


def revisar(geo, log):
    """Busca superficies coplanares que se solapan (parpadean en el juego): suelos a la misma altura
    y paredes en el mismo plano X. Devuelve la lista de problemas."""
    planos = collections.defaultdict(list)
    for ch, by_tex in geo.render.items():
        for tex, seqs in by_tex.items():
            cuads = []
            for sq in seqs:      # una tira en zigzag = cuadriláteros (0,1,3,2), (2,3,5,4)...
                if len(sq) % 2:
                    continue
                for i in range(0, len(sq) - 2, 2):
                    cuads.append([sq[i][0], sq[i + 1][0], sq[i + 3][0], sq[i + 2][0]])
            for P in cuads:
                zs = [p[2] for p in P]
                xs = [p[0] for p in P]
                if max(zs) - min(zs) < 0.002:
                    poly = [(p[0], p[1]) for p in P]
                    if _area(poly) > 1e-3:
                        planos[("z", round(zs[0], 2))].append(_ccw(poly))
                elif max(xs) - min(xs) < 0.002:
                    poly = [(p[1], p[2]) for p in P]
                    if _area(poly) > 1e-3:
                        planos[("x", round(xs[0], 2))].append(_ccw(poly))
                elif max(p[1] for p in P) - min(p[1] for p in P) < 0.002:
                    poly = [(p[0], p[2]) for p in P]
                    if _area(poly) > 1e-3:
                        planos[("y", round(P[0][1], 2))].append(_ccw(poly))
    problemas = []
    for key, polys in planos.items():
        n = len(polys)
        if n < 2:
            continue
        bb = [(min(p[0] for p in q), max(p[0] for p in q), min(p[1] for p in q), max(p[1] for p in q)) for q in polys]
        for i in range(n):
            for j in range(i + 1, n):
                A, B = bb[i], bb[j]
                if A[1] <= B[0] + 0.01 or B[1] <= A[0] + 0.01 or A[3] <= B[2] + 0.01 or B[3] <= A[2] + 0.01:
                    continue
                inter = polys[i]
                cl = polys[j]
                for k in range(len(cl)):
                    inter = _clip(inter, cl[k], cl[(k + 1) % len(cl)])
                    if not inter:
                        break
                if inter and _area(inter) > 0.02:
                    c = (sum(p[0] for p in inter) / len(inter), sum(p[1] for p in inter) / len(inter))
                    problemas.append((key, round(_area(inter), 3), (round(c[0], 1), round(c[1], 1))))
    if problemas:
        log.append(f"REVISIÓN: {len(problemas)} solapes coplanares (pueden parpadear):")
        for k, ar, c in problemas[:25]:
            log.append(f"   plano {k[0]}={k[1]}  área {ar} m²  en {c}")
    else:
        log.append("REVISIÓN: sin superficies coplanares solapadas")
    return problemas


# ======================= Escritura de OMD (render) =======================
def harvest_templates(d031):
    """Cabecera de paquete (0x90 bytes) más usada por cada textura en North Cliffs."""
    off = struct.unpack_from("<I", d031, 4)[0]
    nm = struct.unpack_from("<H", d031, 0x2C)[0]
    pos = off
    cnt = collections.defaultdict(collections.Counter)
    raw = {}
    for _ in range(nm):
        L, nmesh = struct.unpack_from("<IH", d031, pos)
        for mi in range(nmesh):
            ot, nt = struct.unpack_from("<II", d031, pos + 16 + mi * 48 + 36)
            q = pos + ot
            for _ in range(nt):
                nv = d031[q + 0x70]
                t0 = struct.unpack_from("<Q", d031, q + 0x40)[0]
                key = (t0 & 0x3FFF, (t0 >> 37) & 0x3FFF)
                h = bytes(d031[q:q + 0x90])
                sig = h[0x20:0x60] + h[0x74:0x78]
                cnt[key][sig] += 1
                raw.setdefault((key, sig), h)
                q += 0x90 + nv * 32 + 16
        pos += L
    out = {}
    for key, c in cnt.items():
        sig = c.most_common(1)[0][0]
        out[key] = raw[(key, sig)]
    return out


MAXV = 30
UVMAX = 7.4


def pack_sequences(seqs):
    """Trocea tiras largas en tiras de <= 30 vértices y con rango de UV representable."""
    out = []
    for seq in seqs:
        n = len(seq)
        i = 0
        while i < n - 2:
            j = min(n, i + MAXV)
            while True:
                us = [v[1][0] for v in seq[i:j]]
                vs = [v[1][1] for v in seq[i:j]]
                if (max(us) - math.floor(min(us)) <= UVMAX and max(vs) - math.floor(min(vs)) <= UVMAX) or j - i <= 4:
                    break
                j -= 2
            out.append(seq[i:j])
            if j >= n:
                break
            i = j - 2
    return out


def build_omd(by_tex, origin, templates, stats, clut_remap=None):
    """by_tex: {tex: [tiras]} -> bytes de un OMD (1 malla, paquetes con su TEX0)."""
    packets = []
    nverts = 0
    ntris = 0
    first = True
    for tex, seqs in by_tex.items():
        tmpl = templates[tex]
        cur = []
        subs = pack_sequences(seqs)

        def flush(cur):
            nonlocal first, nverts, ntris
            if not cur:
                return
            nv = len(cur)
            h = bytearray(tmpl)
            if clut_remap:
                t0 = struct.unpack_from("<Q", h, 0x40)[0]
                cbp = (t0 >> 37) & 0x3FFF
                if cbp in clut_remap:
                    t0 = (t0 & ~(0x3FFF << 37)) | (clut_remap[cbp] << 37)
                    struct.pack_into("<Q", h, 0x40, t0)
            struct.pack_into("<I", h, 0, 2 * nv + 9)
            h[0x70] = nv
            h[0x8E] = nv * 4
            body = bytearray()
            for (p, uv, col, nrm, adc) in cur:
                x, y, z = to_native(p)
                lx, ly, lz = x - origin[0], y - origin[1], z - origin[2]
                for v in (lx, ly, lz):
                    if not -32760 <= v <= 32760:
                        stats["fuera_rango"] += 1
                nx, ny, nz = to_native(nrm)
                ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                body += struct.pack("<4h4h4h4H",
                                    int(round(clamp(lx, -32760, 32760))), int(round(clamp(ly, -32760, 32760))),
                                    int(round(clamp(lz, -32760, 32760))), 1,
                                    int(nx / ln * 4096), int(ny / ln * 4096), int(nz / ln * 4096), -32768 if adc else 0,
                                    int(round(uv[0] * 4096)), int(round(uv[1] * 4096)), 4096, 0,
                                    int(clamp(col[0], 0, 255)), int(clamp(col[1], 0, 255)), int(clamp(col[2], 0, 255)),
                                    int(clamp(col[3], 0, 128)) if len(col) > 3 else 128)
            tail = bytearray(16)
            tail[15] = 0x14 if first else 0x17
            first = False
            packets.append(bytes(h) + bytes(body) + bytes(tail))
            nverts += nv
            ntris += nv - 2

        for s in subs:
            uo = math.floor(min(v[1][0] for v in s))
            vo = math.floor(min(v[1][1] for v in s))
            verts = [(v[0], (v[1][0] - uo, v[1][1] - vo), v[2], v[3]) for v in s]
            if len(cur) + len(verts) > MAXV:
                flush(cur)
                cur = []
            for k, v in enumerate(verts):
                cur.append((v[0], v[1], v[2], v[3], k < 2))
        flush(cur)
    body = b"".join(packets)
    head = struct.pack("<IHHII", 0x40 + len(body), 1, min(ntris, 65535), nverts, 0)
    mesh = struct.pack("<9f3I", 0, 0, 0, 0, 0, 0, 1, 1, 1, 0x40, len(packets), 0)
    stats["tris"] += ntris
    stats["paquetes"] += len(packets)
    return head + mesh + body


# ======================= Recorte de las texturas de 099 =======================
def _bloques_tex0(t0):
    """Bloques de VRAM (TBP) que lee un TEX0: la textura (por páginas enteras) y su paleta."""
    tbp = t0 & 0x3FFF
    tbw = (t0 >> 14) & 0x3F
    psm = (t0 >> 20) & 0x3F
    tw, th = 1 << ((t0 >> 26) & 0xF), 1 << ((t0 >> 30) & 0xF)
    cbp = (t0 >> 37) & 0x3FFF
    pagina = {0x14: (128, 128), 0x13: (128, 64), 0x00: (64, 32), 0x01: (64, 32), 0x02: (64, 64), 0x0A: (64, 64)}
    if psm not in pagina or tw > 1024 or th > 1024 or tbp == 0:
        return set()          # no es un TEX0 de verdad (bytes que se le parecen)
    pw, ph = pagina[psm]
    ancho = max(tw, tbw * 64)
    paginas = max(1, -(-ancho // pw)) * max(1, -(-th // ph))
    out = set(range(tbp, tbp + paginas * 32))
    if psm in (0x13, 0x14) and cbp:
        out |= set(range(cbp, cbp + 4))
    return out


def recortar_texturas(out, log):
    """Las subidas 0 y 1 del bloque de texturas son dos rectángulos de 128 x 896 (458 KB cada uno) con todas las
    texturas de 099; el mapa portado solo usa las del atlas, las paletas y el agua. Se recorta cada subida a la
    franja de filas que lee algún TEX0 del mapa (modelos, objetos, objetos del suelo, cielo) o la tabla de texturas
    animadas. El resto de la VRAM se queda como esté (nadie la lee)."""
    import kf4_tex as kt
    out = bytearray(out)
    off_tex, off_snd = struct.unpack_from("<II", out, 0x24)
    usados = set()
    for zona in ((0x80, off_tex), (off_snd, len(out))):
        for o in range(zona[0], zona[1] - 16, 16):
            if out[o + 8] == 0x06 and not any(out[o + 9:o + 16]):
                usados |= _bloques_tex0(struct.unpack_from("<Q", out, o)[0])
        # TEX0 de los paquetes de modelo (cabecera 0x90: TEX0 en +0x40 con registro 0x06 en +0x48)
    for k in range(32):           # tabla de texturas animadas (0x1480 copias, 0x1540 dibujos)
        if k < 16:
            b, f, w, hh = struct.unpack_from("<4H", out, 0x1480 + k * 12)
            if b:
                usados |= set(range(b, b + 64))
        else:
            e = out[0x1540 + (k - 16) * 0x28:0x1540 + (k - 15) * 0x28]
            base, cb, tb = struct.unpack_from("<H", e, 6)[0], struct.unpack_from("<H", e, 0x0A)[0], \
                struct.unpack_from("<H", e, 0x1A)[0]
            if tb:
                usados |= set(range(base, base + 64)) | set(range(cb, cb + 4)) | set(range(tb, tb + 0x100))
    blob = bytes(out[off_tex:off_snd])
    _, ups = kt.upload_map_textures(blob, 0, len(blob))
    nuevo = bytearray()
    pos = 0
    ahorro = 0
    for i, u in enumerate(ups):
        o = u["offset"]
        nuevo += blob[pos:o]
        fin = o + 128 + u["bytes"]
        bandas = []
        if i < 2 and u["dpsm"] == 0 and u["dbw"] == 2 and u["w"] == 128 and u["x"] == 0 and u["y"] == 0:
            for blq in usados:
                k = blq - u["dbp"]
                if 0 <= k < (u["h"] // 32) * 64:
                    bandas.append(k // 64)
        if i < 2 and u["dbw"] == 2 and u["w"] == 128 and bandas is not None and u["h"] % 32 == 0:
            if not bandas:
                bandas = [0]
            b0, b1 = min(bandas), max(bandas) + 1
            y0, y1 = b0 * 32, b1 * 32
            datos = blob[o + 128 + y0 * 512:o + 128 + y1 * 512]
            nq = len(datos) // 16
            cab = bytearray(blob[o:o + 128])
            struct.pack_into("<I", cab, 0, nq + 7)                       # tamaño del paquete (qw - 1)
            struct.pack_into("<I", cab, 28, (0x51 << 24) | (nq + 6))     # VIF DIRECTHL: qw que siguen
            tp = struct.unpack_from("<Q", cab, 64)[0]
            tp = (tp & ~(0x7FF << 48)) | (y0 << 48)                       # TRXPOS: DSAY = y0
            struct.pack_into("<Q", cab, 64, tp)
            tr = struct.unpack_from("<Q", cab, 80)[0]
            tr = (tr & ~(0xFFF << 32)) | ((y1 - y0) << 32)                # TRXREG: alto
            struct.pack_into("<Q", cab, 80, tr)
            gi = struct.unpack_from("<Q", cab, 112)[0]
            gi = (gi & ~0x7FFF) | nq                                      # GIF IMAGE: NLOOP
            struct.pack_into("<Q", cab, 112, gi)
            nuevo += cab + datos
            ahorro += u["bytes"] - len(datos)
        else:
            nuevo += blob[o:fin]
        pos = fin
    nuevo += blob[pos:]
    if ahorro <= 0:
        return bytes(out)
    delta = len(nuevo) - len(blob)
    res = bytearray(out[:off_tex]) + nuevo + out[off_snd:]
    struct.pack_into("<I", res, 0x28, off_snd + delta)
    for o in (4, 0xC):                         # punteros internos del banco de sonido
        v = struct.unpack_from("<I", res, off_snd + delta + o)[0]
        struct.pack_into("<I", res, off_snd + delta + o, v + delta)
    struct.pack_into("<I", res, 0x00, len(res))
    log.append(f"Texturas de 099 que no se usan, fuera: {ahorro // 1024} KB menos")
    return bytes(res)


# ======================= Escritura de CSK (colisión) =======================
FUSIONAR_COLISION = True      # juntar los rectángulos de colisión del mismo plano en otros más grandes (--quitar fusion)


def _fusionar_rectangulos(tiras):
    """Las tiras de 4 puntos que son rectángulos alineados con los ejes (suelos de casilla, paredes rectas) se juntan
    con las de su mismo plano que comparten un lado entero: el mismo suelo o pared con muchas menos tiras (cada tira
    son 32 bytes de cabecera + 16 por punto; los niveles del King's Field traen las casillas en trozos pequeños).
    Las demás tiras se quedan como están. Devuelve la lista nueva."""
    grupos = collections.defaultdict(list)
    otras = []
    for t in tiras:
        if len(t) != 4:
            otras.append(t)
            continue
        a, b, c, d = t
        hecho = False
        for eje in range(3):          # el plano: la coordenada que es igual en los 4 puntos
            if max(p[eje] for p in t) - min(p[eje] for p in t) > 1e-4:
                continue
            ua, va = [k for k in range(3) if k != eje]
            us = sorted({round(p[ua], 4) for p in t})
            vs = sorted({round(p[va], 4) for p in t})
            if len(us) != 2 or len(vs) != 2:
                break
            esquinas = {(round(p[ua], 4), round(p[va], 4)) for p in t}
            if len(esquinas) != 4:
                break
            # sentido (la normal del primer triángulo, como la tira original)
            e1 = [b[k] - a[k] for k in range(3)]
            e2 = [c[k] - a[k] for k in range(3)]
            nrm = e1[(eje + 1) % 3] * e2[(eje + 2) % 3] - e1[(eje + 2) % 3] * e2[(eje + 1) % 3]
            clave = (eje, round(a[eje], 4), nrm > 0)
            grupos[clave].append([us[0], us[1], vs[0], vs[1]])
            hecho = True
            break
        if not hecho:
            otras.append(t)
    out = list(otras)
    for (eje, nivel, positivo), rects in grupos.items():
        ua, va = [k for k in range(3) if k != eje]
        for _ in range(2):
            for direccion in (0, 1):          # juntar a lo largo de u (mismo v0, v1) y luego de v
                rects.sort(key=lambda r: (r[2], r[3], r[0]) if direccion == 0 else (r[0], r[1], r[2]))
                juntos = []
                for r in rects:
                    if juntos:
                        q = juntos[-1]
                        if direccion == 0 and q[2] == r[2] and q[3] == r[3] and abs(q[1] - r[0]) < 1e-4:
                            q[1] = r[1]
                            continue
                        if direccion == 1 and q[0] == r[0] and q[1] == r[1] and abs(q[3] - r[2]) < 1e-4:
                            q[3] = r[3]
                            continue
                    juntos.append(list(r))
                rects = juntos
        for u0, u1, v0, v1 in rects:
            def P(u, v):
                p = [0.0, 0.0, 0.0]
                p[eje], p[ua], p[va] = nivel, u, v
                return tuple(p)
            orden = [P(u0, v0), P(u1, v0), P(u0, v1), P(u1, v1)]
            # el mismo sentido que las tiras de las que sale
            e1 = [orden[1][k] - orden[0][k] for k in range(3)]
            e2 = [orden[2][k] - orden[0][k] for k in range(3)]
            nrm = e1[(eje + 1) % 3] * e2[(eje + 2) % 3] - e1[(eje + 2) % 3] * e2[(eje + 1) % 3]
            if (nrm > 0) != positivo:
                orden = [orden[0], orden[2], orden[1], orden[3]]
            out.append(orden)
    return out


TIRA_COLISION_MAX = 48        # puntos como mucho por tira de colisión
TIRA_SENTIDO = False          # True: solo encadenar triángulos que conservan su sentido (los de los modelos del King's
# Field vienen con sentidos mezclados y casi no se juntaba nada; la colisión del 4 ya recibía tiras con sentidos
# mezclados y funcionaba, así que no lo tiene en cuenta)


def _tiras_colision(tiras):
    """Las tiras de colisión (de 3 o más puntos) pasadas a triángulos y vueltas a juntar en tiras largas: cada
    triángulo de más cuesta un punto (16 bytes) en vez de una tira entera (32 + 48). Solo se encadena un triángulo
    si, con el cambio de sentido de las tiras (impar: los dos primeros al revés), queda con su sentido de antes."""
    def k(p):
        return (round(p[0], 3), round(p[1], 3), round(p[2], 3))
    tris = []
    for t in tiras:
        for i in range(len(t) - 2):
            a, b, c = (t[i], t[i + 1], t[i + 2]) if i % 2 == 0 else (t[i + 1], t[i], t[i + 2])
            if len({k(a), k(b), k(c)}) == 3:
                tris.append((a, b, c))
    claves = [tuple(k(v) for v in t) for t in tris]
    por_arista = collections.defaultdict(list)
    for i, kk in enumerate(claves):
        for x, y in ((0, 1), (1, 2), (2, 0)):
            por_arista[frozenset((kk[x], kk[y]))].append(i)

    def mismo_sentido(t1, t2):
        return t2 in (t1, (t1[1], t1[2], t1[0]), (t1[2], t1[0], t1[1]))
    usado = [False] * len(tris)
    out = []
    for i0 in range(len(tris)):
        if usado[i0]:
            continue
        usado[i0] = True
        tira = list(tris[i0])
        kt = list(claves[i0])
        # el primer triángulo, girado para que su último lado sea el que tiene un vecino libre (girarlo no le cambia
        # el sentido)
        for _ in range(3):
            if any(not usado[j] for j in por_arista[frozenset((kt[1], kt[2]))]):
                break
            tira = tira[1:] + tira[:1]
            kt = kt[1:] + kt[:1]
        while len(tira) < TIRA_COLISION_MAX:
            a, b = kt[-2], kt[-1]
            par = (len(tira) - 2) % 2 == 0          # índice del triángulo que se añadiría
            sig = None
            for j in por_arista[frozenset((a, b))]:
                if usado[j]:
                    continue
                kj = claves[j]
                ter = next(q for q in range(3) if kj[q] not in (a, b))
                nuevo = (a, b, kj[ter]) if par else (b, a, kj[ter])
                if not TIRA_SENTIDO or mismo_sentido(kj, nuevo):
                    sig = (j, ter)
                    break
            if sig is None:
                break
            j, ter = sig
            usado[j] = True
            tira.append(tris[j][ter])
            kt.append(claves[j][ter])
        out.append(tira)
    return out


def build_csk(coll, origin, stats):
    """coll: {'wall': [tiras], 'floor': [tiras]} -> bytes de una malla de colisión."""
    if FUSIONAR_COLISION:
        antes = sum(len(v) for v in coll.values())
        coll = {k: _tiras_colision(_fusionar_rectangulos(v)) for k, v in coll.items()}
        stats["coll_fusion"] += antes - sum(len(v) for v in coll.values())
    pts = []
    idx = {}

    def pid(p):
        x, y, z = to_native(p)
        key = (round(x - origin[0], 1), round(y - origin[1], 1), round(z - origin[2], 1))
        if key not in idx:
            idx[key] = len(pts)
            pts.append(key)
        return idx[key]

    lists = []
    # hazard: material (0, FF, FF) = efecto 0 = Player_CollideWithMap pone ground_kills (muerte al caer al mar)
    mats = {"wall": (255, 0, 0), "floor": (0, 255, 0), "hazard": (0, 255, 255)}
    for kind in ("wall", "floor", "hazard"):
        strips = []
        for s in coll.get(kind, []):
            strips.append([pid(p) for p in s])
        lists.append((kind, strips))
    while len(pts) < 4:
        pts.append((0.0, 0.0, 0.0))
    body = bytearray()
    offs = []
    counts = []
    for kind, strips in lists:
        offs.append(0x50 + len(body) if strips else 0)
        counts.append(len(strips))
        m = mats[kind]
        for s in strips:
            body += struct.pack("<HHHH", len(s), 1, 0x48, 0x0C) + bytes(0x18)
            for i in s:
                body += struct.pack("<4I", i, *m)
    points_off = 0x50 + len(body)
    pbytes = b"".join(struct.pack("<4f", *p, 1.0) for p in pts)
    size = points_off + len(pbytes)
    reach = max(math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2) for p in pts)
    # listas del 4: pared, suelo, segunda pared, barrera, hazard, agua
    offs6 = [offs[0], offs[1], 0, 0, offs[2], 0]
    counts6 = [counts[0], counts[1], 0, 0, counts[2], 0]
    head = struct.pack("<4If I", sum(counts), 0x50, points_off, len(pts), reach, size)
    head += struct.pack("<6I", *offs6) + struct.pack("<2I", 0, 0) + struct.pack("<6H", *counts6) + bytes(0x50 - 0x44)
    stats["coll_strips"] += sum(counts)
    stats["coll_points_max"] = max(stats["coll_points_max"], len(pts))
    if len(pts) > 1000:
        # Collision_TransformMeshPoints escribe los puntos en el scratchpad desde 0x70000100: más de 1008 se salen
        stats["coll_demasiados"] += 1
    return head + bytes(body) + pbytes


# ======================= Montaje del mapa =======================
def bounds_native(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _paquetes_tex(d):
    """Los 8 huecos del bloque de texturas, recorridos como Map_ParseFile: (DBP o None, bytes).
    Un hueco vacío es una quadword a cero. Papel de cada hueco (map.c, entity_pool.c, effect.c):
      0, 1: texturas del mapa (se suben antes de dibujar los registros) · 2: registros tardíos
      3: página de texturas de enemigos y objetos con esqueleto · 4: efectos · 5: paletas · 6, 7: extra"""
    a = struct.unpack_from("<I", d, 0x24)[0]
    b = struct.unpack_from("<I", d, 0x28)[0]
    out = []
    pos = a
    for _ in range(8):
        if pos + 16 > b:
            out.append((None, bytes(16)))
            continue
        qw = struct.unpack_from("<I", d, pos)[0]
        size = (qw + 1) * 16
        dbp = (struct.unpack_from("<Q", d, pos + 48)[0] >> 32) & 0x3FFF if qw else None
        out.append((dbp, bytes(d[pos:pos + size])))
        pos += size
    return out


CIELO_TBP = 0x3A80            # textura del cielo de 099 (y de 002, 004, 013): CT32 128x128, TBW 2
CIELO_FOG = 31                # bloque de niebla propio del cielo (el 3 de 099: sin niebla)
CIELO_LUZ = 30                # bloque de luz propio del cielo (el 3 de 099)
RELLENO = 0                   # prueba: bytes de relleno en el mapa (--relleno MB)
RECORTAR_TABLAS = False       # True: quitar enemigos/objetos si las tablas no caben en el hueco de 099 (--recortar)
QUITAR = set()                # partes que se dejan fuera para buscar un fallo (--quitar)
OFF_ANIM = 0x1480 - 0x80      # texturas animadas dentro de los bloques de cabecera (que empiezan en 0x80)


AGUA_DST, AGUA_SRC, AGUA_CLUT = 0x3140, 0x3240, 0x3280     # los de kf_malla.py
# capas del agua: (modo de mezcla, escala, desplazamiento u, v por fotograma), las mismas que el agua de 000
CAPAS_AGUA = [(0x0A, 1.0, -2, -2), (0x48, 2.0, -2, -2), (0x42, 1.0, 0, -4), (0x48, 1.0, 2, 2)]


def poner_agua_animada(blocks, log):
    """Grupo 1 de la tabla de texturas animadas (entradas 4..7; el 0..3 es el cielo): cuatro capas del agua del
    King's Field (PSMT8 en AGUA_SRC) que se desplazan y se mezclan en AGUA_DST, como hace 000 con la suya."""
    base = OFF_ANIM
    for k, (modo, esc, du, dv) in enumerate(CAPAS_AGUA):
        e = bytearray(0x28)
        struct.pack_into("<3H", e, 0x00, 128, 128, 0x13)
        struct.pack_into("<HH", e, 0x06, AGUA_SRC, 0)
        struct.pack_into("<H", e, 0x0A, AGUA_CLUT)
        struct.pack_into("<2f", e, 0x0C, esc, esc)
        struct.pack_into("<2H", e, 0x14, 128, 128)
        struct.pack_into("<HH", e, 0x18, 0, AGUA_DST)
        e[0x1C:0x20] = bytes([0x80, 0x80, 0x80, 0x80])
        struct.pack_into("<HBB", e, 0x20, modo, 1, 1)
        struct.pack_into("<hh", e, 0x24, du, dv)
        o = base + 0xC0 + (4 + k) * 0x28
        blocks[o:o + 0x28] = e
    # cabecera del grupo 1 (en 000: 0x13 y 0x1B)
    struct.pack_into("<H", blocks, base + 0x18 + 0x02, 0x13)
    struct.pack_into("<H", blocks, base + 0x18 + 0x0E, 0x1B)
    log.append("Agua animada: 4 capas que se desplazan (como el agua de 000)")


def textura_nubes(semilla=7, n=128):
    """Nubes que se repiten sin costura (el domo del cielo repite la textura): ruido fractal periódico."""
    import numpy as np
    rng = np.random.default_rng(semilla)
    total = np.zeros((n, n))
    peso = 0.0
    for octava, amp in ((4, 1.0), (8, 0.55), (16, 0.3), (32, 0.16)):
        g = rng.random((octava, octava))
        t = np.arange(n) * octava / n
        i0 = np.floor(t).astype(int)
        f = t - i0
        f = f * f * (3 - 2 * f)
        i1 = (i0 + 1) % octava
        fila = g[i0][:, i0] * (1 - f)[None, :] + g[i0][:, i1] * f[None, :]
        fila2 = g[i1][:, i0] * (1 - f)[None, :] + g[i1][:, i1] * f[None, :]
        total += amp * (fila * (1 - f)[:, None] + fila2 * f[:, None])
        peso += amp
    total /= peso
    c = np.clip((total - 0.36) / 0.34, 0, 1) ** 1.3          # nube: 0 = cielo limpio, 1 = nube densa
    cielo = np.array([118, 134, 156], float)      # encapotado, como los exteriores del 4
    nube = np.array([214, 216, 220], float)
    sombra = np.array([140, 144, 152], float)
    base = cielo[None, None] * (1 - c[..., None]) + nube[None, None] * c[..., None]
    hueco = np.clip((total - 0.62) / 0.2, 0, 1)[..., None]   # la panza de las nubes gruesas, más gris
    base = base * (1 - 0.35 * hueco) + sombra[None, None] * 0.35 * hueco
    img = np.zeros((n, n, 4), np.uint8)
    img[..., :3] = np.clip(base, 0, 255).astype(np.uint8)
    img[..., 3] = 0x80
    return img


def poner_cielo_en_texturas(tex_blob, img, log):
    """Escribe la textura del cielo dentro del paquete 2 (el de 099 sube 128x512 en 32 bits desde 0x3840:
    la textura de TBP 0x3A80 son sus filas 288..415). Devuelve el bloque nuevo o None si no tiene esa forma."""
    out = bytearray(tex_blob)
    pos = 0
    for k in range(8):
        if pos + 16 > len(out):
            return None
        qw = struct.unpack_from("<I", out, pos)[0]
        size = (qw + 1) * 16
        if k == 2:
            if not qw:
                return None
            bitblt = struct.unpack_from("<Q", out, pos + 48)[0]
            trxreg = struct.unpack_from("<Q", out, pos + 80)[0]
            dbp, dbw, psm = (bitblt >> 32) & 0x3FFF, (bitblt >> 48) & 0x3F, (bitblt >> 56) & 0x3F
            w, h = trxreg & 0xFFF, (trxreg >> 32) & 0xFFF
            fila0 = (CIELO_TBP - dbp) // 0x40 * 32
            if psm != 0 or dbw != 2 or w != 128 or (CIELO_TBP - dbp) % 0x40 or fila0 + 128 > h:
                log.append(f"(el paquete 2 no tiene sitio para el cielo: {dbp:04X} {w}x{h})")
                return None
            dat = pos + 128 + fila0 * 128 * 4
            out[dat:dat + 128 * 128 * 4] = img.tobytes()
            return bytes(out)
        pos += size
    return None


def _copiar_bloques_clut(pk099, pk031, mapping):
    """Paquete de paletas (64 px de ancho, PSMCT32) de 099 con las paletas de 031 copiadas encima.
    mapping: {cbp en 031: cbp destino}. Se emula el swizzle del GS para mover bloques enteros."""
    def bloques(pk):
        bitblt = struct.unpack_from("<Q", pk, 48)[0]
        trxreg = struct.unpack_from("<Q", pk, 80)[0]
        dbp = (bitblt >> 32) & 0x3FFF
        dbw = (bitblt >> 48) & 0x3F
        w, h = trxreg & 0xFFF, (trxreg >> 32) & 0xFFF
        return dbp, dbw, w, h

    def addr32(bp, bw, x, y):
        BLOCK32 = (0, 1, 4, 5, 16, 17, 20, 21, 2, 3, 6, 7, 18, 19, 22, 23,
                   8, 9, 12, 13, 24, 25, 28, 29, 10, 11, 14, 15, 26, 27, 30, 31)
        COLW32 = (0, 1, 4, 5, 8, 9, 12, 13, 2, 3, 6, 7, 10, 11, 14, 15)
        page = x // 64 + (y // 32) * bw
        px, py = x % 64, y % 32
        block = BLOCK32[px // 8 + (py // 8) * 8]
        bx, by = px % 8, py % 8
        return bp * 256 + (page * 2048 + block * 64 + (by // 2) * 16 + COLW32[bx + (by % 2) * 8]) * 4

    def to_vram(pk, vram):
        dbp, dbw, w, h = bloques(pk)
        data = pk[128:]
        i = 0
        for y in range(h):
            for x in range(w):
                a = addr32(dbp, max(1, dbw), x, y)
                vram[a:a + 4] = data[i:i + 4]
                i += 4

    v99 = bytearray(4 * 1024 * 1024)
    v31 = bytearray(4 * 1024 * 1024)
    to_vram(pk099, v99)
    to_vram(pk031, v31)
    for src, dst in mapping.items():
        v99[dst * 256:dst * 256 + 256] = v31[src * 256:src * 256 + 256]
    dbp, dbw, w, h = bloques(pk099)
    data = bytearray()
    for y in range(h):
        for x in range(w):
            a = addr32(dbp, max(1, dbw), x, y)
            data += v99[a:a + 4]
    return pk099[:128] + bytes(data)


def bloque_texturas(d099, d031, log):
    """Bloque de texturas con el orden de paquetes de 099 (el juego usa los paquetes 3 y 5 para las
    texturas y paletas de enemigos y objetos, y el 4 para efectos):
      0, 1: texturas de North Cliffs (las de las piezas del valle)
      2:    se sube con los registros tardíos; aquí repite el 4 para no pisar las texturas del valle
      3, 4: página de enemigos y de efectos de 099 (los escarabajos y demás se ven bien)
      5:    paletas de 099 con las paletas del valle metidas en los huecos que usaban las piezas de 099
      6, 7: los de 099
    Devuelve (bytes, {cbp de 031: cbp nuevo})."""
    p99 = _paquetes_tex(d099)
    p31 = _paquetes_tex(d031)
    ok = (p31[0][0] == 0x2E40 and p31[1][0] == 0x3540 and p31[5][0] == 0x3D40 and p99[5][0] == 0x3D40
          and p99[3][0] is not None)
    if not ok:
        log.append("AVISO: bloque de texturas con otra forma; se usa el de 031 tal cual")
        a = struct.unpack_from("<I", d031, 0x24)[0]
        b = struct.unpack_from("<I", d031, 0x28)[0]
        return d031[a:b], {}
    usados31 = sorted({f["CBP"] for f in _tex_piezas(d031)})
    usados99 = {f["CBP"] for f in _tex_piezas(d099)} - {0}
    libres = sorted(c for c in usados99 if 0x3D40 <= c < 0x3E80)
    mapping = {}
    for c in usados31:
        if c in usados99:
            mapping[c] = c           # ya era un hueco de paletas de mapa en 099
    resto = [c for c in usados31 if c not in mapping]
    huecos = [c for c in libres if c not in mapping.values()]
    for c in resto:
        mapping[c] = huecos.pop(0)
    clut = _copiar_bloques_clut(p99[5][1], p31[5][1], mapping)
    vacio = bytes(16)
    paquetes = [p31[0][1], p31[1][1], vacio, p99[3][1], p99[4][1], clut, p99[6][1], p99[7][1]]
    log.append("Texturas: piezas con las de North Cliffs; enemigos, efectos y objetos con las de 099; "
               f"paletas movidas {', '.join(f'{a:04X}->{b:04X}' for a, b in mapping.items() if a != b) or 'ninguna'}")
    return b"".join(paquetes), {a: b for a, b in mapping.items() if a != b}


def _tex_piezas(d):
    off_models = struct.unpack_from("<I", d, 0x04)[0]
    count = struct.unpack_from("<H", d, 0x2C)[0]
    out = []
    pos = off_models
    for _ in range(count):
        length, nmesh = struct.unpack_from("<IH", d, pos)
        if length <= 0:
            break
        for mi in range(nmesh):
            off_ts, n_ts = struct.unpack_from("<II", d, pos + 0x10 + mi * 48 + 36)
            p = pos + off_ts
            for _ in range(n_ts):
                t0 = struct.unpack_from("<Q", d, p + 0x40)[0]
                out.append({"TBP": t0 & 0x3FFF, "CBP": (t0 >> 37) & 0x3FFF})
                p += 0x90 + d[p + 0x70] * 32 + 16
        pos += length
    return out


def _tabla_kinds(d):
    nrec, nfb, nobj, nsp, nit = struct.unpack_from("<5H", d, 0x3C)
    p = md.OFF_RECORDS + nrec * md.REC + nfb * md.FLAGBLK + md.NEIGH_N * md.NEIGH + nobj * md.OBJREC \
        + nsp * md.SPAWNREC + nit * md.ITEMREC
    kinds = [k for k in struct.unpack_from("<32h", d, p)]
    out = []
    for k in kinds:
        if k < 0:
            break
        out.append(k)
    return out, p


# ---------- índice del disco: lo que se copia de los mapas originales, leído una sola vez ----------
VERSION_INDICE = 4


def _trozo(src, nombre, off, n):
    """n bytes desde off de un archivo del disco, sin leer el archivo entero."""
    v = src.names[nombre.lower()]
    if isinstance(v, str):
        with open(v, "rb") as f:
            f.seek(off)
            return f.read(n)
    with open(src.path, "rb") as f:
        f.seek(v[0] + off)
        return f.read(min(n, max(0, v[1] - off)))


def _mapas_de(src):
    return sorted(n for n in src.names if len(n) == 7 and n.endswith(".map") and n[:3].isdigit())


def indice_disco(src, log):
    """Recorre una vez todos los mapas del disco y guarda en kf4_valle/indice_disco.pkl:
      spawns: {registro chr.prm: spawn de 0x60 bytes} (el primero que aparece de cada uno)
      items:  {modelo de objeto: (mapa, desplazamiento, tamaño)} (modelo + textura de lo que se tira al suelo)
      objetos:{def de obj.prm: plantilla} de cofre, puerta y losa
    Solo lee la cabecera y las tablas de cada mapa (y las secciones de objetos de los pocos que hacen falta), y
    las siguientes veces sale del archivo: antes se leían cientos de MB de la ISO en cada generación."""
    import pickle
    try:
        st = os.stat(src.path)
        clave = (VERSION_INDICE, os.path.abspath(src.path), st.st_size, int(st.st_mtime), len(src.names))
    except OSError:
        clave = None
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kf4_valle", "indice_disco.pkl")
    if "indice" in QUITAR:            # prueba: sin el archivo y en el orden de antes (alfabético, 099 primero)
        clave = None
    if clave and os.path.isfile(ruta):
        try:
            with open(ruta, "rb") as f:
                idx = pickle.load(f)
            if idx.get("clave") == clave:
                return idx
        except Exception:
            pass
    print("Preparando el índice de los mapas del disco (solo la primera vez)...")
    spawns, items, objetos = {}, {}, {}
    todos_spawns = []
    falta_obj = set(OBJ_TODOS)
    mapas = _mapas_de(src)
    # como antes de haber índice: modelos de objeto con 099 primero; cofres, puertas y losas con 011, 012 y 004
    # primero; los enemigos se ordenan aparte (alfabético)
    mapas.sort(key=lambda n: (n != "099.map", n))
    mapas_obj = sorted(mapas, key=lambda n: (n not in ("011.map", "012.map", "004.map"), n))
    for nm in mapas:
        try:
            cab = _trozo(src, nm, 0, 0x80)
            off_models = struct.unpack_from("<I", cab, 0x04)[0]
            if not 0x17C0 <= off_models < 0x200000:
                continue
            t = _trozo(src, nm, 0, off_models)
            for sp in spawns_de(t):
                todos_spawns.append((nm, struct.unpack_from("<H", sp, 0x30)[0], sp))
            kinds, _ = _tabla_kinds(t)
            off_item = struct.unpack_from("<I", t, 0x20)[0]
            off_script = struct.unpack_from("<I", t, 0x4C)[0]
            if kinds and off_script > off_item and any(k not in items for k in kinds):
                sec = _trozo(src, nm, off_item, off_script - off_item)
                pos = 0
                for k in kinds:
                    a = pos
                    pos += struct.unpack_from("<I", sec, pos)[0]
                    pos += struct.unpack_from("<I", sec, pos)[0]
                    items.setdefault(k, (nm, off_item + a, pos - a))
        except (struct.error, KeyError, IndexError):
            continue
    for nm in mapas_obj:
        if not falta_obj:
            break
        try:
            t = _trozo(src, nm, 0, struct.unpack_from("<I", _trozo(src, nm, 0, 0x80), 0x04)[0])
            defs = {struct.unpack_from("<H", o, 0x30)[0] for o in _objetos_de(t)}
            if falta_obj & defs:
                sub = plantillas_objetos_de(src.read(nm), nm, falta_obj)
                objetos.update(sub)
                falta_obj -= set(sub)
        except (struct.error, KeyError, IndexError):
            continue
    # cada registro, del primer mapa por orden alfabético que lo tenga (como se hacía cuando funcionaba)
    for nm, r, sp in sorted(todos_spawns, key=lambda x: x[0]):
        spawns.setdefault(r, sp)
    idx = {"clave": clave, "spawns": spawns, "items": items, "objetos": objetos}
    if clave:
        try:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta, "wb") as f:
                pickle.dump(idx, f)
        except OSError:
            pass
    log.append(f"Índice del disco: {len(mapas)} mapas, {len(spawns)} enemigos, {len(items)} modelos de objeto")
    return idx


def modelos_de_items(src, modelos, log):
    """El modelo y la textura de cada objeto que se tira por el suelo, de los mapas originales (índice del disco).
    modelos: números de modelo (item_nam.prm, campo 0x30). Devuelve {modelo: bytes del modelo + textura}."""
    idx = indice_disco(src, log)
    out, falta = {}, []
    for k in modelos:
        e = idx["items"].get(k)
        if e is None:
            falta.append(k)
            continue
        out[k] = _trozo(src, e[0], e[1], e[2])
    if falta:
        log.append(f"(no encontré el modelo de estos objetos: {sorted(falta)})")
    return out


# enemigos de la zona 1: (mapa de donde se copia el spawn, registro chr.prm, hueco de pool)
ENEMIGOS = {
    "escarabajo": ("099.map", 11, 2),
    "planta": ("000.map", 0, 0),
    "seta": ("031.map", 87, 3),
    "murcielago": ("026.map", 10, 1),
}
LUZ_ENEMIGOS = 24     # bloque de luz propio para los enemigos
LUZ_OBJETOS_KF = 25   # bloque de luz de los objetos del mapa portado (puertas, paredes secretas, cofres, barriles):
# la luna fría de los enemigos los dejaba gris azulados al lado de las paredes del King's Field, que son oscuras y
# cálidas; esta es tenue y cálida, para que la pared que se abre no se distinga de las de al lado
LUZ_PANEL_AMB = 0.5
LUZ_PANEL = 26        # la pared secreta del King's Field: su luz va en sus colores de vértice (los del mapa): sin luces
LUZ_OBJETOS_KF_COLORES = [(0.30, 0.27, 0.20, 0.0), (0.12, 0.10, 0.07, 0.0), (0.05, 0.05, 0.05, 0.0),
                          (0.30, 0.28, 0.24, 1.0)]
MAX_POOLS = 4         # huecos de pool de enemigos que se usan (026 usa 5; 4 es lo probado en el valle)
POOL_DINAMICO = True  # todos los enemigos con hueco 0xFF (el juego los carga y descarga según cerca: sin límite de tipos)
DISTANCIA_ENEMIGOS = 4500   # cm: a esta distancia del jugador se cargan y aparecen
MAX_SPAWNS = 120      # el 4: 128 entidades por mapa y 256 ids de spawn (entity_world.c); el cuelgue que se vio con 46 era el banco de sonido movido


def spawns_de(d):
    nrec, nfb, nobj, nsp, nit = struct.unpack_from("<5H", d, 0x3C)
    sp = md.OFF_RECORDS + nrec * md.REC + nfb * md.FLAGBLK + md.NEIGH_N * md.NEIGH + nobj * md.OBJREC
    return [bytes(d[sp + i * md.SPAWNREC:sp + (i + 1) * md.SPAWNREC]) for i in range(nsp)]


def _limpiar_spawn(sp, pool):
    b = bytearray(sp)
    b[0x34] = pool                      # hueco de pool propio por tipo
    struct.pack_into("<H", b, 0x36, 0)  # sin script de muerte del mapa original
    b[0x3A] = 0xFF                      # niebla y luz: las del registro que pisa
    b[0x3B] = 0xFF
    b[0x42] = 0
    b[0x43] = 0
    struct.pack_into("<H", b, 0x4E, 0)  # sin diálogo
    struct.pack_into("<H", b, 0x58, 0)
    return bytes(b)


def plantillas_chr(src, registros, log):
    """{"chr:N": spawn} para registros de chr.prm cualesquiera (los mapas portados de otros King's Field).
    Se copia un spawn real de ese registro de cualquier mapa del disco (lleva su modo de IA, radio, vuelo...);
    si no hay ninguno, uno de otro registro del mismo tipo de bicho; si tampoco, el del escarabajo de 099."""
    out = {}
    if not registros:
        return out
    try:
        prm = src.read("param/chr.prm")
        tipo_de = {i: prm[i * 0x450 + 2] for i in range(len(prm) // 0x450)}
    except Exception:
        tipo_de = {}
    spawns = indice_disco(src, log)["spawns"]
    por_tipo = {}
    for r, sp in spawns.items():
        t = tipo_de.get(r)
        if t is not None:
            por_tipo.setdefault(t, sp)
    import kf4_pulpo
    for r in registros:
        sp = spawns.get(r)
        if r == kf4_pulpo.REGISTRO_PULPO:       # el pulpo: registro nuevo, con el spawn de la Flor oscura
            sp = spawns.get(kf4_pulpo.REGISTRO_BASE) or por_tipo.get(tipo_de.get(kf4_pulpo.REGISTRO_BASE))
            if sp is not None:
                b = bytearray(sp)
                struct.pack_into("<H", b, 0x30, r)
                out[f"chr:{r}"] = _limpiar_spawn(bytes(b), 0)
                continue
        if sp is None:
            sp = por_tipo.get(tipo_de.get(r))
            if sp is None:
                sp = spawns.get(11)
                log.append(f"(no hay ningún spawn del registro {r} ni de su tipo: se usa el del escarabajo)")
            else:
                log.append(f"(el registro {r} no sale en ningún mapa: se usa un spawn de otro de su mismo tipo)")
            if sp is None:
                continue
            b = bytearray(sp)
            struct.pack_into("<H", b, 0x30, r)
            sp = bytes(b)
        out[f"chr:{r}"] = _limpiar_spawn(sp, 0)
    return out


def plantillas_enemigos(src, log, tipos=()):
    """Copia, de los mapas originales, un spawn de cada enemigo de la zona 1 (y de los "chr:N" que se pidan)."""
    out = plantillas_chr(src, sorted({int(t[4:]) for t in tipos if str(t).startswith("chr:")}), log)
    spawns = indice_disco(src, log)["spawns"]
    if "plantilla" in QUITAR and src.has("099.map"):
        # prueba: todos los "chr:N" sobre el spawn del escarabajo del propio 099, cambiando solo el registro
        base = next((sp for sp in spawns_de(src.read("099.map")) if struct.unpack_from("<H", sp, 0x30)[0] == 11),
                    None)
        if base:
            for t in list(out):
                b = bytearray(base)
                struct.pack_into("<H", b, 0x30, int(t[4:]))
                out[t] = _limpiar_spawn(b, 0)
            log.append("PRUEBA: todos los enemigos con el spawn del escarabajo de 099")
    for tipo, (mapa, chr_id, pool) in ENEMIGOS.items():
        sp = spawns.get(chr_id)
        if sp is None:
            log.append(f"(no encontré el spawn de {tipo} en el disco)")
            continue
        out[tipo] = _limpiar_spawn(sp, pool)
    return out


# objetos que se copian de otros mapas para los mapas portados: def de obj.prm -> uso
#   187: cofre de madera (clase 4: se abre con X y da el objeto de +0x44)
#    18: puerta de madera que se abre (clase 6)
#    80: losa de pared que se aparta (clase 6; en 011/012 son las paredes que se abren), con la textura del mapa
#     2: barril que se rompe a golpes (clase 21, contenedor: suelta lo que lleva, en +0x44)
OBJ_COFRE, OBJ_PUERTA, OBJ_SECRETA, OBJ_BARRIL = 187, 18, 80, 2
OBJ_TODOS = {OBJ_COFRE: "cofre", OBJ_PUERTA: "puerta", OBJ_SECRETA: "secreta", OBJ_BARRIL: "barril"}


def secciones_objeto(d):
    """(modelos simples, colisiones, movimientos) de un mapa, cada uno una lista de bytes; None si no cuadra."""
    o_m, o_s, o_c, o_mo, o_i = (struct.unpack_from("<I", d, o)[0] for o in (0x0C, 0x10, 0x14, 0x18, 0x20))
    n_m, n_s, n_c, n_mo = struct.unpack_from("<4H", d, 0x30)
    modelos, p = [], o_m
    for _ in range(n_m):
        a = struct.unpack_from("<I", d, p)[0]
        a += struct.unpack_from("<I", d, p + a)[0]
        modelos.append(bytes(d[p:p + a]))
        p += a
    if p != o_s:
        return None
    colis, p = [], o_c
    for _ in range(n_c):
        a = struct.unpack_from("<I", d, p + 0x14)[0]
        colis.append(bytes(d[p:p + a]))
        p += a
    if p != o_mo:
        return None
    movs, p = [], o_mo
    for _ in range(n_mo):
        a = struct.unpack_from("<I", d, p)[0]
        if a <= 0:
            return None
        movs.append(bytes(d[p:p + a]))
        p += a
    if p > o_i:
        return None
    return modelos, colis, movs


def _objetos_de(d):
    nrec, nfb, nobj, nsp, nit = struct.unpack_from("<5H", d, 0x3C)
    p = md.OFF_RECORDS + nrec * md.REC + nfb * md.FLAGBLK + md.NEIGH_N * md.NEIGH
    return [bytes(d[p + i * md.OBJREC:p + (i + 1) * md.OBJREC]) for i in range(nobj)]


def plantillas_objetos_de(d, nm, quiero):
    """Plantillas (rec, modelo, colisión, movimiento, tam) de los defs de 'quiero' que tenga el mapa d."""
    out = {}
    secc = secciones_objeto(d)
    if secc is None:
        return out
    modelos, colis, movs = secc
    for o in _objetos_de(d):
        di, mi, ci, mo = struct.unpack_from("<4H", o, 0x30)
        if di not in quiero or di in out or mi >= len(modelos):
            continue
        if di == OBJ_PUERTA and struct.unpack_from("<H", o, 0x3A)[0]:
            continue                     # las de 011 con +0x3A piden algo para abrirse: otra sin eso
        try:
            info, _ = md.parse_omd(modelos[mi], 0, False, [], nm)
            tam = tuple(info["max"][k] - info["min"][k] for k in range(3))
        except Exception:
            tam = (200.0, 200.0, 20.0)
        out[di] = {"rec": o, "modelo": modelos[mi], "colision": colis[ci] if ci < len(colis) else None,
                   "movimiento": movs[mo] if mo < len(movs) else None, "tam": tam, "mapa": nm}
    return out


def plantillas_objetos(src, log):
    """{def: {"rec", "modelo", "colision", "movimiento", "tam"}} de cofre, puerta y losa (índice del disco)."""
    out = dict(indice_disco(src, log)["objetos"])
    for di in sorted(set(OBJ_TODOS) - set(out)):
        log.append(f"(no encontré en el disco el objeto {di} ({OBJ_TODOS[di]}): no se ponen)")
    if out:
        log.append("Plantillas de objetos: " + ", ".join(f"{OBJ_TODOS[k]} de {v['mapa']}" for k, v in out.items()))
    return out


def _retexturar(modelo, tex, uvmap=None):
    """Cambia la textura (TEX0) de los paquetes que usan una textura de mapa (PSMT4/8 fuera del hueco de
    objetos 0x3940) por tex = (tbp, cbp, tbw, w, h, psm). Para la losa: que tenga la pared del propio mapa."""
    import math
    b = bytearray(modelo)
    tbp, cbp, tbw, w, h, psm = tex
    length = struct.unpack_from("<I", b, 0)[0]
    nmesh = struct.unpack_from("<H", b, 4)[0]
    for mi in range(nmesh):
        mo = 0x10 + mi * 48
        off_ts, n_ts = struct.unpack_from("<II", b, mo + 36)
        pos = off_ts
        for _ in range(n_ts):
            if pos + 0x90 > length:
                break
            t0 = struct.unpack_from("<Q", b, pos + 0x40)[0]
            viejo = t0 & 0x3FFF
            if viejo and not (0x3940 <= viejo < 0x3B40):
                t0 &= ~((0x3FFF) | (0x3F << 14) | (0x3F << 20) | (0xF << 26) | (0xF << 30) | (0x3FFF << 37))
                t0 |= tbp | (tbw << 14) | (psm << 20) | (int(math.log2(w)) << 26) | (int(math.log2(h)) << 30) \
                    | (cbp << 37)
                struct.pack_into("<Q", b, pos + 0x40, t0)
                if uvmap:
                    # la región del atlas donde está la textura de pared del King's Field que la rodea: las UV
                    # del modelo (0..1) pasan a ese cuadro, para que la losa no se distinga de la pared
                    ax, ay, lado, W, H = uvmap
                    for v in range(b[pos + 0x70]):
                        q = pos + 0x90 + v * 32 + 16
                        u, vv = struct.unpack_from("<2h", b, q)
                        u = min(max(u / 4096.0, 0.0), 1.0)
                        vv = min(max(vv / 4096.0, 0.0), 1.0)
                        struct.pack_into("<2h", b, q, int(round((ax + u * (lado - 0.5)) / W * 4096)),
                                         int(round((ay + vv * (lado - 0.5)) / H * 4096)))
            nv = b[pos + 0x70]
            pos += 0x90 + nv * 32 + 16
    return bytes(b)


def _registro_de(cajas, x, z):
    """El registro (trozo) que contiene el punto, o el más cercano."""
    mejor, dist = 0, 1e30
    for k, ((a0, _, a2), (b0, _, b2)) in cajas:
        dx = max(a0 - x, 0, x - b0)
        dz = max(a2 - z, 0, z - b2)
        if dx * dx + dz * dz < dist:
            mejor, dist = k, dx * dx + dz * dz
    return mejor


def panel_kf(t, tris):
    """La losa del 4 (t: plantilla del def 80) con la pared de verdad del King's Field: tris = [(textura, 3 x
    (punto del editor, uv, color, normal))]. Devuelve (modelo, colisión, registro de objeto, movimiento) o None.
    La losa se deja como en el 4 (su caja de colisión de 200 x 300 x 20, intacta): se gira para que su lado fino
    vaya con el grosor de la pared y se escala a la medida de la pared; los puntos de la pared se pasan a su
    espacio (sin giro ni escala). Así choca y se abre como la losa del 4."""
    import math
    if not tris:
        return None
    pts = [to_native(v[0]) for _, tri in tris for v in tri]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    z0, z1 = min(p[2] for p in pts), max(p[2] for p in pts)
    y_pie = max(p[1] for p in pts)                       # Y hacia abajo: el pie es la Y mayor
    alto = y_pie - min(p[1] for p in pts)
    # lo que tiene que subir: la parte de abajo de la pared (hasta el techo; la de encima está dentro de la roca)
    alto_paso = alto              # (la parte de encima del techo ya no viene: kf_malla)
    cx, cz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
    fino_x = (x1 - x0) < (z1 - z0)
    # giro: el eje z de la losa (su grosor) en el eje fino de la pared (door.c: mundo = (x cos + z sen, -x sen + z cos))
    ang = math.pi / 2 if fino_x else 0.0
    ca, sa = math.cos(ang), math.sin(ang)
    ancho = (z1 - z0) if fino_x else (x1 - x0)
    grueso = max((x1 - x0) if fino_x else (z1 - z0), 20.0)
    # la misma escala en x y z: el juego escala en los ejes del mundo y no en los de la losa (con sx != sz y el
    # giro de 90 grados la pared salía más delgada, metida en su hueco, y se veían los lados del marco);
    # con la misma, da igual el orden. La caja de colisión queda de 200 x 20 por esa escala (más fina que la pared)
    sx = sz = ancho / 200.0
    sy = (alto_paso + 10.0) / 300.0
    m = bytearray(t["modelo"])
    length = struct.unpack_from("<I", m, 0)[0]
    nmesh = struct.unpack_from("<H", m, 4)[0]
    if nmesh != 2:
        return None
    off0, n0 = struct.unpack_from("<II", m, 0x10 + 36)
    off1, n1 = struct.unpack_from("<II", m, 0x10 + 48 + 36)
    if off0 > off1:
        return None
    cab1 = bytes(m[off1:off1 + 0x90])                    # cabecera de paquete de la losa (plantilla)
    pos = off1
    for _ in range(n1):
        pos += 0x90 + m[pos + 0x70] * 32 + 16
    fin_paquetes = pos
    # por textura, muchos triángulos en cada paquete (3 puntos por triángulo, los 2 primeros sin dibujar: ADC):
    # un paquete por triángulo eran 256 bytes cada uno y las puertas no cabían en el mapa
    por_tex = collections.OrderedDict()
    for tex, tri in tris:
        por_tex.setdefault(tex, []).append(tri)
    paquetes = []
    TRI_PAQ = MAXV // 3            # (como el mapa: 30 puntos por paquete; h[0x8E] es un byte)
    for tex, lista_t in por_tex.items():
        tbp, cbp, tbw, w, hh, psm = tex
        for i0 in range(0, len(lista_t), TRI_PAQ):
            trozo = lista_t[i0:i0 + TRI_PAQ]
            nv = 3 * len(trozo)
            h = bytearray(cab1)
            t0 = struct.unpack_from("<Q", h, 0x40)[0]
            t0 &= ~((0x3FFF) | (0x3F << 14) | (0x3F << 20) | (0xF << 26) | (0xF << 30) | (0x3FFF << 37))
            t0 |= tbp | (tbw << 14) | (psm << 20) | (int(math.log2(w)) << 26) | (int(math.log2(hh)) << 30) | (cbp << 37)
            struct.pack_into("<Q", h, 0x40, t0)
            struct.pack_into("<I", h, 0, 2 * nv + 9)
            h[0x70] = nv
            h[0x8E] = (nv * 4) & 0xFF
            cuerpo = bytearray()
            for kt, tri in enumerate(trozo):
                orden = (0, 1, 2) if kt % 2 == 0 else (1, 0, 2)      # la tira cambia el sentido en cada impar
                for k, idx in enumerate(orden):
                    p, uv, col, n = tri[idx]
                    x, y, z = to_native(p)
                    dx, dz = x - cx, z - cz
                    lx, lz = dx * ca - dz * sa, dx * sa + dz * ca        # el giro de la losa, deshecho
                    lx, ly, lz = lx / sx, (y - y_pie) / sy, lz / sz
                    nx, ny, nz = n[0], -n[2], n[1]
                    nx, nz = nx * ca - nz * sa, nx * sa + nz * ca
                    nx, ny, nz = nx / sx, ny / sy, nz / sz
                    ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                    cuerpo += struct.pack("<4h4h4h4H", int(round(clamp(lx, -32000, 32000))),
                                          int(round(clamp(ly, -32000, 32000))), int(round(clamp(lz, -32000, 32000))), 1,
                                          int(nx / ln * 4096), int(ny / ln * 4096), int(nz / ln * 4096),
                                          -32768 if k < 2 else 0,
                                          int(round(uv[0] * 4096)), int(round(uv[1] * 4096)), 4096, 0,
                                          int(clamp(col[0], 0, 255)), int(clamp(col[1], 0, 255)),
                                          int(clamp(col[2], 0, 255)), 128)
            cola = bytearray(16)
            cola[15] = 0x14 if not paquetes else 0x17
            paquetes.append(bytes(h) + bytes(cuerpo) + bytes(cola))
    nuevo = bytearray(m[:off1]) + b"".join(paquetes) + m[fin_paquetes:length]
    nuevo_len = len(nuevo)
    nuevo += m[length:]                                  # la parte de textura propia del objeto, tal cual
    struct.pack_into("<I", nuevo, 0, nuevo_len)
    struct.pack_into("<H", nuevo, 6, min(65535, len(tris) + 3))
    struct.pack_into("<I", nuevo, 8, 3 * len(tris) + 5)
    struct.pack_into("<II", nuevo, 0x10 + 48 + 36, off1, len(paquetes))
    b = bytearray(t["rec"])
    struct.pack_into("<4f", b, 0x00, cx, y_pie, cz, 0.0)
    struct.pack_into("<4f", b, 0x10, 0.0, ang, 0.0, 0.0)
    struct.pack_into("<4f", b, 0x20, sx, sy, sz, 1.0)
    # que no la cierre el 4 por su cuenta (door.c: MapObject_UpdateOpenDoor la cierra si este campo es 0 y el jugador
    # está más lejos que su alcance + 1 m, y su alcance es pequeño: se cerraba estando al lado). La cierra su guion,
    # cuando te alejas PANEL_CIERRE (_guion_panel)
    b[0x46] = 0 if "cierre" in QUITAR else 1      # prueba: --quitar cierre, como en la revisión 7
    # el movimiento: la losa sube 280 (el juego suma ese desplazamiento a la posición sin escalarlo,
    # map_object/door.c); la pared del King's Field es más alta: que suba toda su altura
    mov = t["movimiento"]
    if mov:
        mov = bytearray(mov)
        # el desplazamiento del movimiento va en unidades de la losa (la escala y del objeto lo multiplica: con más
        # subía por encima de su hueco y se veía el corte): que suba justo su altura
        sube = alto_paso / sy
        for viejo, nuevo_v in ((-280.0, -sube), (280.0, sube)):
            a_, b_ = struct.pack("<f", viejo), struct.pack("<f", nuevo_v)
            k = mov.find(a_)
            while k >= 0:
                if k % 4 == 0:
                    mov[k:k + 4] = b_
                k = mov.find(a_, k + 4)
        mov = bytes(mov)
    return bytes(nuevo), t["colision"], b, mov


def colocar_objetos_kf(objs, obj_secc, lista, plantillas, recs, log, tex_pared=None):
    """Añade cofres, puertas y losas (lista de dicts del mapa portado: tipo, pos, giro, escala, objeto) a la tabla
    de objetos y a sus secciones. Devuelve (objs, obj_secc, nº añadidos)."""
    if not lista or not plantillas or not obj_secc:
        return objs, obj_secc, 0
    (nm, ns, nc, nmo), (sec_m, sec_s, sec_c, sec_mo) = obj_secc
    sec_m, sec_c, sec_mo = bytearray(sec_m), bytearray(sec_c), bytearray(sec_mo)
    indice = {}
    objs = bytearray(objs)
    cuenta = collections.Counter()
    defs = {"cofre": OBJ_COFRE, "puerta": OBJ_PUERTA, "secreta": OBJ_SECRETA, "barril": OBJ_BARRIL}
    cajas = [(k, r["box"]) for k, r in enumerate(recs) if "box" in r]
    for o in lista:
        di = defs.get(o["tipo"])
        t = plantillas.get(di)
        if t is None:
            continue
        if o.get("panel") and di == OBJ_SECRETA:
            hecho = panel_kf(t, o["panel"])
            if hecho:
                modelo, colis, b, mov = hecho
                sec_m += modelo
                sec_c += colis
                imo = 0xFFFF
                if mov:
                    sec_mo += mov
                    imo = nmo
                    nmo += 1
                struct.pack_into("<4H", b, 0x30, di, nm, nc, imo)
                nm += 1
                nc += 1
                x, _, z = struct.unpack_from("<3f", b, 0)
                struct.pack_into("<H", b, 0x38, _registro_de(cajas, x, z))
                b[0x3D] = LUZ_PANEL
                # al usarla, su guion: la abre (señal a la puerta), tiembla la cámara y el mando y suena (GUIONES_PANEL)
                usados = {o_[0x3A] for o_ in _trozos_de(objs, md.OBJREC)} | {g[1] for g in GUIONES_PANEL}
                ident = next((i_ for i_ in range(PANEL_ID0, 256) if i_ not in usados), None)
                if ident is not None:
                    b[0x3A] = ident
                    etiqueta = GUION_PANEL0 + len(GUIONES_PANEL)
                    struct.pack_into("<H", b, 0x40, etiqueta)
                    GUIONES_PANEL.append((etiqueta, ident, struct.unpack_from("<3f", b, 0), bool(o.get("es_puerta"))))
                objs += b
                cuenta["pared secreta del King's Field"] += 1
                continue
        clave_tex, uvmap = None, None
        if di == OBJ_SECRETA and tex_pared:
            elegido = tex_pared(o) if callable(tex_pared) else (tex_pared, None)
            if elegido:
                clave_tex, uvmap = elegido
        clave = (di, clave_tex, uvmap)
        if clave not in indice:           # modelo, colisión y movimiento: una vez por tipo (y textura)
            modelo = t["modelo"]
            if clave_tex:
                modelo = _retexturar(modelo, clave_tex, uvmap)
            sec_m += modelo
            im = nm
            nm += 1
            ic = 0xFFFF
            if t["colision"]:
                sec_c += t["colision"]
                ic = nc
                nc += 1
            imo = 0xFFFF
            if t["movimiento"]:
                sec_mo += t["movimiento"]
                imo = nmo
                nmo += 1
            indice[clave] = (im, ic, imo)
        im, ic, imo = indice[clave]
        b = bytearray(t["rec"])
        x, y, z = to_native(o["pos"])
        struct.pack_into("<4f", b, 0x00, x, y, z, 0.0)
        struct.pack_into("<4f", b, 0x10, 0.0, o.get("giro", 0.0), 0.0, 0.0)
        ancho, alto = (o.get("medida") or [None, None]) + [None] * (2 - len(o.get("medida") or []))
        tx, ty, tz = (max(v, 1.0) for v in t["tam"])
        sx = ancho * 100.0 / tx if ancho else 1.0
        sy = alto * 100.0 / ty if alto else sx
        # la pared secreta: un bloque que llena la casilla (como la del King's Field), no una losa fina: así
        # tapa el hueco entero se mire desde donde se mire (y el giro da igual)
        sz = sx if di != OBJ_SECRETA else (ancho or 2.5) * 100.0 / tz
        struct.pack_into("<4f", b, 0x20, sx, sy, sz, 1.0)
        struct.pack_into("<4H", b, 0x30, di, im, ic, imo)
        # registro (trozo) donde está: el que lo contiene, o el más cercano
        mejor, dist = 0, 1e30
        for k, ((a0, _, a2), (b0, _, b2)) in cajas:
            dx = max(a0 - x, 0, x - b0)
            dz = max(a2 - z, 0, z - b2)
            if dx * dx + dz * dz < dist:
                mejor, dist = k, dx * dx + dz * dz
        struct.pack_into("<H", b, 0x38, mejor)
        b[0x3D] = LUZ_OBJETOS_KF
        if di == OBJ_COFRE:
            struct.pack_into("<h", b, 0x44, int(o.get("objeto", 0)))
            b[0x56] = 0
        elif di == OBJ_BARRIL and int(o.get("objeto", 0)):
            struct.pack_into("<h", b, 0x44, int(o["objeto"]))   # lo que suelta al romperse (si no, la hierba)
        objs += b
        cuenta[o["tipo"]] += 1
    if cuenta:
        log.append("Objetos del mapa portado: " + ", ".join(f"{n} {t}" for t, n in cuenta.items()))
    return bytes(objs), ((nm, ns, nc, nmo), [bytes(sec_m), sec_s, bytes(sec_c), bytes(sec_mo)]), sum(cuenta.values())


# La fuente del Palacio (099) cura con un guion (etiqueta 0x44D): mira la vida, saca el efecto de la fuente
# (efecto 800, en el jugador) y llena la vida (AddPlayerHp 999). Lo dispara un objeto vacío (def 512) al
# examinarlo con X (player/interact.c: use_script). Ese guion antes mira si la fuente está purificada (con el
# cristal): aquí se copia sin esa condición, con una etiqueta nueva.
GUION_FUENTE_099 = 0x44D
GUION_FUENTE = 0x0F0D
FUENTE_ALTO = 120.0          # el punto que se examina, sobre el suelo (cm)


# La pared secreta del King's Field, al abrirse: un guion por pared (etiqueta GUION_PANEL0 + n) que la abre con
# una señal (como hacen los guiones de 011 con sus puertas: SignalMapObject id 1), hace temblar la cámara despacio
# (ShakeCamera), vibra el mando (RumblePad) y suena (PlaySoundAt, sonido común: el de la losa del 4 es del banco de
# 011 y en este mapa no suena). Los números, como en los guiones del juego.
GUION_PANEL0 = 0x0F20
PANEL_ID0 = 200                  # ids de objeto (MapObject_GetById, byte 0x3A) para las paredes
PANEL_TEMBLOR = (2.5, 75)        # alcance y fotogramas del temblor de la cámara (000 usa 8.0, 30 en un terremoto)
PANEL_VIBRACION = (64, 75)       # fuerza y fotogramas de la vibración del mando (los de 099: 64, 15)
PANEL_SONIDO = 0x0D              # sonido común (el de los movimientos 6 y 7 de la losa del 4)
PANEL_CIERRE = 800               # cm: se cierra cuando te alejas más que esto
PANEL_ESPERA = 150               # fotogramas abierta como mínimo antes de mirar la distancia
GUIONES_PANEL = []               # [(etiqueta, id, posición)] de este mapa (colocar_objetos_kf los llena)


def _trozos_de(b, n):
    return [b[i:i + n] for i in range(0, len(b) - n + 1, n)]


def _guion_panel(etiqueta, ident, pos, puerta=False):
    E, F = 0x40000, 0x60000
    fl = lambda v: struct.unpack("<I", struct.pack("<f", v))[0]
    x, y, z = pos
    w = [(0x190 << 16) | etiqueta]
    w += [(182 << 16) | 2, E, ident, E, 1]                                   # SignalMapObject id 1: se abre
    if not puerta:            # las puertas solo suenan; la pared secreta, además, tiembla
        w += [(144 << 16) | 2, F, fl(PANEL_TEMBLOR[0]), E, PANEL_TEMBLOR[1]]      # ShakeCamera
        w += [(198 << 16) | 3, E, PANEL_VIBRACION[0], E, PANEL_VIBRACION[1], E, 0]   # RumblePad
    w += [(160 << 16) | 6, E, 0, E, PANEL_SONIDO, F, fl(0.0), F, fl(x), F, fl(y - 150.0), F, fl(z)]   # PlaySoundAt
    # se cierra cuando el jugador se aleja más de PANEL_CIERRE cm (el cierre del 4, por su alcance, la bajaba
    # enseguida aunque estuvieras al lado): espera, mira la distancia cada medio segundo y entonces la cierra
    LX, LZ, D1, D2 = (0x60002, 0), (0x60002, 4), (0x60002, 8), (0x60002, 12)   # variables float del hilo
    PX, PZ = (0x60201, 0), (0x60201, 8)                                         # posición del jugador (x, z)
    SUB, MUL, ADD, FIN = (1 << 8) | 4, (2 << 8) | 4, (0 << 8) | 4, 0xFF

    def set_(dest, a, op, b):
        # el operando de la palabra "set" es cuántas palabras la siguen (Script_SkipWord salta eso: con 0, quien
        # buscara una etiqueta más abajo se perdía dentro del guion y el juego se colgaba al cargar el mapa)
        return [(0x196 << 16) | 8, dest[0], dest[1], a[0], a[1], op, b[0], b[1], FIN]
    if "cierre" in QUITAR:          # prueba: sin el bucle que la cierra (la cierra el 4, como en la revisión 7)
        return w + [0x191 << 16]
    w += [(1 << 16) | 1, E, PANEL_ESPERA]                                        # Wait
    bucle = len(w)
    w += set_(LX, PX, SUB, (F, fl(x)))
    w += set_(LZ, PZ, SUB, (F, fl(z)))
    w += set_(D1, LX, MUL, LX)
    w += set_(D2, LZ, MUL, LZ)
    w += set_(D1, D1, ADD, D2)
    cerrar = [(182 << 16) | 2, E, ident, E, 0, 0x191 << 16]                    # SignalMapObject id 0: se cierra
    w += [(0x192 << 16) | (1 << 8), len(cerrar), D1[0], D1[1], 2, F, fl(float(PANEL_CIERRE) ** 2)]   # si d² >
    w += cerrar
    w += [(1 << 16) | 1, E, 30]                                                  # si no: espera 30 y vuelve
    salto = len(w)
    w += [(0x197 << 16) | ((bucle - (salto + 1)) & 0xFFFF)]
    w += [0x191 << 16]
    return w


def guion_paneles(guion, log):
    if not GUIONES_PANEL:
        return guion
    g = _palabras(guion)
    fin = g.index((0x190 << 16) | 0x7FFE)
    nuevo = []
    for etiqueta, ident, pos, puerta in GUIONES_PANEL:
        nuevo += _guion_panel(etiqueta, ident, pos, puerta)
    g2 = g[:fin] + nuevo + g[fin:]
    malas = _etiquetas_perdidas(g2, [e for e, _, _, _ in GUIONES_PANEL])
    if malas:
        log.append(f"AVISO: el guion de las paredes no se lee bien (etiquetas {malas}): sin guion, para no colgar el juego")
        return guion
    g = g2
    log.append(f"Paredes secretas y puertas: {len(GUIONES_PANEL)} con su guion al abrirse (sonido; las paredes, temblor)")
    return struct.pack("<%dI" % len(g), *g) + bytes(len(guion) % 4)


def _etiquetas_perdidas(g, etiquetas):
    """Las etiquetas que el juego no encontraría recorriendo el guion como Script_Start (Script_SkipWord), más la
    final 0x7FFE: si sale alguna, buscar un guion se saldría del guion y el juego se cuelga."""
    vistas, i = set(), 0
    while i < len(g):
        w = g[i]
        op, arg = w >> 16, w & 0xFFFF
        if op == 0x190:
            vistas.add(arg)
            if arg == 0x7FFE:
                break
        i += 1
        if op in (0x190, 0x191, 0x194, 0x195, 0x197):
            pass
        elif op == 0x192:
            i += (arg >> 8) * 5 + 1
        elif op == 0x196:
            i += arg
        elif op == 0x19D:
            i += arg + 1
        else:
            i += arg * 2
    return [hex(e) for e in list(etiquetas) + [0x7FFE] if e not in vistas]


def _palabras(b):
    return list(struct.unpack_from("<%dI" % (len(b) // 4), b, 0))


def guion_fuente(guion, d099, log):
    """El guion del mapa con la cura de la fuente (etiqueta GUION_FUENTE) delante de la etiqueta final."""
    o_s = struct.unpack_from("<I", d099, 0x4C)[0]
    o_t = struct.unpack_from("<I", d099, 0x24)[0]
    w = _palabras(d099[o_s:o_t])
    try:
        i = w.index((0x190 << 16) | GUION_FUENTE_099)
    except ValueError:
        log.append("AVISO: no encontré el guion de la fuente en 099; las fuentes no curan")
        return guion
    # [etiqueta] [if 1 comparación: purificada] [GetPlayerHp] [if vida < máxima] [efecto] [AddPlayerHp] [salto]...
    if w[i + 1] >> 16 != 0x192 or (w[i + 1] >> 8) & 0xFF != 1:
        log.append("AVISO: el guion de la fuente de 099 no es el que conozco; las fuentes no curan")
        return guion
    a = i + 2 + 1 + 5                     # tras el if: palabras a saltar + 2 args (2 palabras) + comparación
    b = a
    while w[b] >> 16 != 0x197:            # hasta el salto que se salta el aviso de "vida llena"
        b += 1
    cuerpo = [(0x190 << 16) | GUION_FUENTE] + w[a:b] + [0x191 << 16]
    g = _palabras(guion)
    fin = g.index((0x190 << 16) | 0x7FFE)
    g[fin:fin] = cuerpo
    log.append("Fuentes: curan con el guion y el efecto de las del Palacio")
    return struct.pack("<%dI" % len(g), *g) + bytes(len(guion) % 4)


def fuentes_que_curan(h, objs, fuentes, recs, log):
    """Un objeto vacío (como el de la fuente de 099) en cada fuente, con el guion de la cura."""
    plantilla = None
    for o in _objetos_de(h):
        if struct.unpack_from("<H", o, 0x40)[0] == GUION_FUENTE_099:
            plantilla = bytearray(o)
            break
    if plantilla is None:
        plantilla = bytearray(md.OBJREC)
        struct.pack_into("<4f", plantilla, 0x20, 2.0, 2.0, 2.0, 1.0)
        struct.pack_into("<4H", plantilla, 0x30, 512, 0xFFFF, 0xFFFF, 0xFFFF)
    struct.pack_into("<HH", plantilla, 0x40, GUION_FUENTE, 0)
    struct.pack_into("<H", plantilla, 0x58, 0)            # sin guion de usar un objeto (el cristal)
    cajas = [(k, r["box"]) for k, r in enumerate(recs) if "box" in r]
    objs = bytearray(objs)
    for p in fuentes:
        x, y, z = to_native(p)
        y -= FUENTE_ALTO
        b = bytearray(plantilla)
        struct.pack_into("<4f", b, 0x00, x, y, z, 0.0)
        mejor, dist = 0, 1e30
        for k, ((a0, _, a2), (b0, _, b2)) in cajas:
            dx = max(a0 - x, 0, x - b0)
            dz = max(a2 - z, 0, z - b2)
            if dx * dx + dz * dz < dist:
                mejor, dist = k, dx * dx + dz * dz
        struct.pack_into("<H", b, 0x38, mejor)
        objs += b
    return bytes(objs), len(fuentes)


def recortar_objetos(h, objs, nobj, obj_kind, log):
    """Los objetos del Palacio (estatuas, puertas, antorchas...) no se usan en el valle pero sus modelos
    ocupan 1,2 MB. Se deja solo el punto de guardado: el resto pasa a ser un objeto vacío (def 512, sin
    modelo ni colisión), así los índices de objeto del script siguen siendo válidos.
    Devuelve ((nº modelos, nº articulados, nº colisiones, nº movimientos), [4 secciones]) o None."""
    if not obj_kind:
        return None
    o_m, o_s, o_c, o_mo, o_i = (struct.unpack_from("<I", h, o)[0] for o in (0x0C, 0x10, 0x14, 0x18, 0x20))
    n_m, n_s, n_c, n_mo = struct.unpack_from("<4H", h, 0x30)
    # tramos de cada modelo simple (modelo + textura) y de cada colisión
    modelos, p = [], o_m
    for _ in range(n_m):
        a = struct.unpack_from("<I", h, p)[0]
        a += struct.unpack_from("<I", h, p + a)[0]
        modelos.append(bytes(h[p:p + a]))
        p += a
    if p != o_s:
        log.append("AVISO: no pude recorrer los modelos de objeto; se dejan como estaban")
        return None
    colis, p = [], o_c
    for _ in range(n_c):
        a = struct.unpack_from("<I", h, p + 0x14)[0]
        colis.append(bytes(h[p:p + a]))
        p += a
    if p != o_mo:
        log.append("AVISO: no pude recorrer las colisiones de objeto; se dejan como estaban")
        return None
    sec_m, sec_c = bytearray(), bytearray()
    nm = nc = 0
    for i in range(nobj):
        o = i * md.OBJREC
        di, mi, ci, mo = struct.unpack_from("<4H", objs, o + 0x30)
        if obj_kind.get(di) == 20 and mi < n_m and mo == 0xFFFF:
            sec_m += modelos[mi]
            struct.pack_into("<H", objs, o + 0x32, nm)
            objs[o + 0x3D] = LUZ_ENEMIGOS   # su bloque de luz forzado (el 18 de 099) está vacío aquí: salía negro
            nm += 1
            if ci < n_c:
                sec_c += colis[ci]
                struct.pack_into("<H", objs, o + 0x34, nc)
                nc += 1
        else:
            struct.pack_into("<4H", objs, o + 0x30, 512, 0xFFFF, 0xFFFF, 0xFFFF)
            struct.pack_into("<HH", objs, o + 0x40, 0, 0)     # sin scripts de uso/rotura
    ahorro = (o_i - o_m) - len(sec_m) - len(sec_c)
    log.append(f"Objetos del Palacio quitados ({ahorro // 1024} KB libres); queda el punto de guardado")
    return (nm, 0, nc, 0), [bytes(sec_m), b"", bytes(sec_c), b""]


def assemble(valle, d099, d031, rumbo, log, plantillas=None, item_modelo=None, modelos_item=None, obj_kind=None,
             bloque_cruz=None, plantillas_obj=None):
    GUIONES_PANEL.clear()
    stats = collections.Counter()
    if getattr(valle, "tex_fuente", "031") == "099":
        # la zona usa las texturas del propio 099 (piedra clara, columnas, sillares): bloque tal cual
        a_, b_ = struct.unpack_from("<II", d099, 0x24)
        tex_blob, clut_remap = bytes(d099[a_:b_]), {}
        templates = harvest_templates(d099)
        log.append("Texturas: las de 099 (Palacio de Oath) tal cual")
        for nueva, base in (getattr(valle, "kf_plantillas", None) or {}).items():
            if base in templates:      # misma cabecera de paquete, con la paleta propia de esa región
                t = bytearray(templates[base])
                t0 = struct.unpack_from("<Q", t, 0x40)[0]
                if nueva == (AGUA_DST, 0):
                    # el agua animada: textura de 32 bits 128x128 (la compone el juego cada fotograma)
                    t0 &= ~((0x3FFF) | (0x3F << 14) | (0x3F << 20) | (0xF << 26) | (0xF << 30) | (0x3FFF << 37)
                            | (0x7 << 61))
                    t0 |= AGUA_DST | (2 << 14) | (0 << 20) | (7 << 26) | (7 << 30)
                    struct.pack_into("<Q", t, 0x40, t0)
                else:
                    struct.pack_into("<Q", t, 0x40, (t0 & ~(0x3FFF << 37)) | (nueva[1] << 37))
                # sin mipmaps: muchas cabeceras de 099 llevan TEX1 con MXL=1 y dirección automática (0x...364), y el
                # nivel 1 de la textura del 4 que hay detrás del hueco sale de lejos con la paleta del King's Field
                # (el suelo "amarillento" a distancia). 0x60: filtro lineal, sin niveles.
                for o in range(0x20, 0x70, 0x10):
                    if t[o + 8] == 0x14 and not any(t[o + 9:o + 16]):
                        struct.pack_into("<Q", t, o, 0x60)
                templates[nueva] = bytes(t)
    else:
        tex_blob, clut_remap = bloque_texturas(d099, d031, log)
        templates = harvest_templates(d031)
    stats["coll_points_max"] = 0
    niebla = getattr(valle, "niebla", FOG_RGB)
    niebla_k = getattr(valle, "niebla_k", 520000.0)
    geo = valle.geo
    chunks = sorted(set(list(geo.render.keys()) + list(geo.coll.keys())))
    omds, csks, recs = [], [], []
    for ch in chunks:
        by_tex = geo.render.get(ch, {})
        allp = [v[0] for seqs in by_tex.values() for s in seqs for v in s]
        cp = [p for kind in ("wall", "floor", "hazard") for s in geo.coll.get(ch, {}).get(kind, []) for p in s]
        if not allp and not cp:
            continue
        ref = allp or cp
        # origen en el centro de la caja del trozo (también en altura): así las coordenadas locales caben
        # en int16 (±327 m) aunque el trozo sea muy alto, como la torre
        cx = (min(p[0] for p in ref) + max(p[0] for p in ref)) / 2
        cy = (min(p[1] for p in ref) + max(p[1] for p in ref)) / 2
        cz = (min(p[2] for p in ref) + max(p[2] for p in ref)) / 2
        origin = to_native((cx, cy, cz))
        rec = {"origin": origin, "omd": -1, "csk": -1}
        if ch[0] == "A":
            # agua: registro tardío (bit 0 de las marcas, como el agua de 000/016/026/099): se dibuja después de
            # componer la textura animada (modo 1 de la tabla) y por encima de lo demás, transparente
            rec["tarde"] = True
        if allp:
            # trocear si el OMD es enorme
            omd = build_omd(by_tex, origin, templates, stats, clut_remap)
            rec["omd"] = len(omds)
            omds.append(omd)
            nat = [to_native(p) for p in allp]
            rec["box"] = bounds_native(nat)
        if cp:
            csk = build_csk(geo.coll[ch], origin, stats)
            rec["csk"] = len(csks)
            csks.append(csk)
            nat = [to_native(p) for p in cp]
            rec["cbox"] = bounds_native(nat)
        recs.append(rec)

    # cielo: el domo de 099 (registro 0, con la marca de cielo 0x80000000), centrado en la zona
    cielo = None
    if getattr(valle, "cielo", False) and getattr(valle, "tex_fuente", "031") == "099" and "cielo" not in QUITAR:
        r0 = bytes(d099[md.OFF_RECORDS:md.OFF_RECORDS + md.REC])
        o0 = struct.unpack_from("<h", r0, 0x30)[0]
        if struct.unpack_from("<I", r0, 0x3C)[0] & 0x80000000 and o0 >= 0:
            p = struct.unpack_from("<I", d099, 0x04)[0]
            for _ in range(o0):
                p += struct.unpack_from("<I", d099, p)[0]
            todos = [v[0] for c in geo.render.values() for seqs in c.values() for s_ in seqs for v in s_]
            if todos:
                cx = (min(q[0] for q in todos) + max(q[0] for q in todos)) / 2
                cy = (min(q[1] for q in todos) + max(q[1] for q in todos)) / 2
                cz = min(q[2] for q in todos)
                recs.append({"raw": r0, "origin": to_native((cx, cy, cz)), "omd": len(omds), "csk": -1})
                omds.append(bytes(d099[p:p + struct.unpack_from("<I", d099, p)[0]]))
                cielo = True
                log.append("Cielo: el domo de nubes del 4 sobre la zona")

    h = d099
    off_models = struct.unpack_from("<I", h, 0x04)[0]
    off_coll = struct.unpack_from("<I", h, 0x08)[0]
    off_objm = struct.unpack_from("<I", h, 0x0C)[0]
    off_tex = struct.unpack_from("<I", h, 0x24)[0]
    off_snd = struct.unpack_from("<I", h, 0x28)[0]
    omd_blob = b"".join(omds)
    csk_blob = b"".join(csks)
    room_m = off_coll - off_models
    room_c = off_objm - off_coll
    log.append(f"Piezas OMD: {len(omds)}  {len(omd_blob)} bytes de {room_m} disponibles")
    log.append(f"Colisiones CSK: {len(csks)}  {len(csk_blob)} bytes de {room_c} disponibles")
    log.append(f"Registros: {len(recs)}  triángulos {stats['tris']}  paquetes {stats['paquetes']}  "
               f"tiras de colisión {stats['coll_strips']}  máx. puntos por colisión {stats['coll_points_max']}")
    if stats["coll_demasiados"]:
        log.append(f"AVISO GRAVE: {stats['coll_demasiados']} colisiones pasan de 1000 puntos (el juego admite 1008)")
    if stats["fuera_rango"]:
        log.append(f"AVISO: {stats['fuera_rango']} coordenadas fuera de int16 (se han recortado)")
    # las secciones se localizan por la cabecera: si la geometría no cabe en su hueco se desplaza el resto

    # --- tablas ---
    nrec0, nfb, nobj, nsp, nit = struct.unpack_from("<5H", h, 0x3C)
    p = md.OFF_RECORDS + nrec0 * md.REC
    flag_blocks = h[p:p + nfb * md.FLAGBLK]
    p += nfb * md.FLAGBLK
    neigh = h[p:p + md.NEIGH_N * md.NEIGH]
    p += md.NEIGH_N * md.NEIGH
    objs = bytearray(h[p:p + nobj * md.OBJREC])
    p += nobj * md.OBJREC
    spawns = bytearray(h[p:p + nsp * md.SPAWNREC])
    p += nsp * md.SPAWNREC
    items = bytearray(h[p:p + nit * md.ITEMREC])

    # objetos de 099: lejos (1 km), para que no estorben
    for i in range(nobj):
        o = i * md.OBJREC
        x = struct.unpack_from("<f", objs, o)[0]
        struct.pack_into("<f", objs, o, x + 100000.0)
    # enemigos: copias de los spawns originales (plantas, setas, murciélagos, escarabajos) sobre las cornisas
    plantillas = dict(plantillas or {})
    if "escarabajo" not in plantillas and nsp:
        b = bytearray(spawns[:md.SPAWNREC])
        b[0x3A] = b[0x3B] = 0xFF
        plantillas["escarabajo"] = bytes(b)
    nuevos = bytearray()
    cuenta = collections.Counter()
    # cada tipo de enemigo en su hueco de pool (los de la zona 1 ya traen el suyo, 0..3); los "chr:N" de un
    # mapa portado se reparten por frecuencia en los huecos que queden
    frec = collections.Counter(t if t in plantillas else "escarabajo" for t, _ in valle.enemigos)
    pools = {t: ENEMIGOS[t][2] for t in frec if t in ENEMIGOS}
    libres = [p for p in range(MAX_POOLS) if p not in pools.values()]
    for t, _ in frec.most_common():
        if t not in pools:
            pools[t] = libres.pop(0) if libres else None
    if POOL_DINAMICO:
        # hueco de pool 0xFF: el juego da a cada tipo el primer bloque libre (o el que lleva más tiempo sin usarse)
        # cuando un enemigo suyo está cerca y lo suelta cuando no queda ninguno (entity_pool.c, Entity_StartLoadsInRange):
        # los tipos se cargan y se descargan solos según dónde estés, sin el límite de 4-5 por mapa. Lo usan los mapas
        # originales con muchos tipos (008: 6 tipos, todos en 0xFF)
        pools = {t: 0xFF for t in frec}
    quitados = collections.Counter()
    enemigos = []
    for tipo, pos in valle.enemigos:
        t = tipo if tipo in plantillas else "escarabajo"
        if pools.get(t) is None:
            quitados[tipo] += 1
            continue
        enemigos.append((t, pos))
    if quitados:
        log.append(f"AVISO: más de {MAX_POOLS} tipos de enemigo; fuera: {dict(quitados)}")
    if len(enemigos) > MAX_SPAWNS:
        log.append(f"AVISO: {len(enemigos)} enemigos; se dejan {MAX_SPAWNS}")
        enemigos = [enemigos[i * len(enemigos) // MAX_SPAWNS] for i in range(MAX_SPAWNS)]
    # +0x32: número de tipo de enemigo dentro del mapa (en los originales va 0, 1, 2... por tipo; las plantillas
    # traen el de su mapa: un 3 o un 8 con un solo tipo en el mapa cuelga la carga)
    orden_tipo = {}
    for t, _ in enemigos:
        orden_tipo.setdefault(t, len(orden_tipo))
    for k, (tipo, pos) in enumerate(enemigos):
        b = bytearray(plantillas[tipo])
        b[0x34] = pools[tipo]
        struct.pack_into("<H", b, 0x32, orden_tipo[tipo])
        x, y, z = to_native(pos)
        struct.pack_into("<3f", b, 0x00, x, y - 10.0, z)
        struct.pack_into("<f", b, 0x14, valle.rng.uniform(0, 6.283))
        b[0x3C] = k & 0xFF                         # id de spawn único
        # distancia a la que se carga (despawn_range, 0x5A): a 0 el juego pone 20 m y los esqueletos salían de
        # golpe delante; los mapas grandes del 4 (000) usan 48-65 m y sin límite vertical se cargan pisos enteros
        struct.pack_into("<H", b, 0x5A, DISTANCIA_ENEMIGOS)
        struct.pack_into("<H", b, 0x48, 800)       # vertical_despawn_range, como 000
        nuevos += b
        cuenta[tipo] += 1
    spawns = nuevos
    nsp = len(enemigos)
    log.append("Enemigos: " + ", ".join(f"{n} {t}" for t, n in cuenta.items()))
    for t, txt in getattr(valle, "_tam_chr", {}).items():
        if t in cuenta:
            log.append(f"  {t}: {txt}")
    # objetos por el suelo: modelos copiados de los mapas originales, tabla de tipos y umbrales
    kinds99, kp = _tabla_kinds(h)
    plantilla_item = bytes(items[:md.ITEMREC]) if nit else bytes(md.ITEMREC)
    item_modelo = item_modelo or {}
    modelos_item = dict(modelos_item or {})
    lista = []
    for item, pos in getattr(valle, "objetos", []):
        mdl = item_modelo.get(item)
        if mdl is None or mdl not in modelos_item:
            continue
        lista.append((item, mdl, pos))
    kinds = []
    for _, mdl, _ in lista:
        if mdl not in kinds and len(kinds) < 32:
            kinds.append(mdl)
    lista = [x for x in lista if x[1] in kinds][:48]
    items = bytearray()
    for i, (item, mdl, pos) in enumerate(lista):
        b = bytearray(plantilla_item)
        x, y, z = to_native(pos)
        struct.pack_into("<4f", b, 0x00, x, y - 5.0, z, 0.0)
        struct.pack_into("<4f", b, 0x10, 0.0, valle.rng.uniform(0, 6.283), 0.0, 0.0)
        struct.pack_into("<H", b, 0x30, item)
        struct.pack_into("<H", b, 0x34, 0)     # sin script al cogerlo
        b[0x36] = 0                            # sin condición
        b[0x37] = 100                          # aparece siempre
        b[0x38] = 0                            # grupo 0 (umbral 100)
        b[0x3F] = i                            # hueco propio
        items += b
    nit = len(lista)
    tabla_tipos = struct.pack("<32h", *(kinds + [-1] * (32 - len(kinds))))
    umbrales = bytes([100] + [0] * 15)
    item_blob = b"".join(modelos_item[k] for k in kinds)
    log.append(f"Objetos por el suelo: {nit} ({len(kinds)} modelos distintos)")
    # punto de guardado de 099 dentro de la sala grande
    if obj_kind and getattr(valle, "guardado", None):
        for i in range(nobj):
            o = i * md.OBJREC
            di = struct.unpack_from("<H", objs, o + 0x30)[0]
            if obj_kind.get(di) == 20:
                x, y, z = to_native(valle.guardado)
                struct.pack_into("<3f", objs, o, x, y, z)
                log.append("Punto de guardado colocado en la sala grande")
                break
    obj_secc = recortar_objetos(h, objs, nobj, obj_kind, log)
    if obj_secc and getattr(valle, "kf_objetos", None) and plantillas_obj:
        muro = None
        try:
            import kf4_editor
            import kf_malla
            tbp, cbp = kf4_editor.TEXTURAS["muro"]
            tbw, w_, h_ = kf_malla.FORMATO_HUECOS["muro"]
            muro = (tbp, cbp, tbw, w_, h_, 0x14)
            pared_kf = getattr(valle, "kf_pared_en", None)
            if pared_kf:                 # la textura de la pared de King's Field que rodea cada losa
                muro_fijo = muro
                muro = lambda o: o.get("tex_kf") or pared_kf(o["pos"]) or (muro_fijo, None)
        except Exception:
            pass
        lista = list(valle.kf_objetos)
        paneles = getattr(valle, "kf_paneles", None) or {}
        if paneles:
            # la pared secreta: el objeto que sube es la pared de verdad del King's Field (su modelo de MO.T, con
            # sus texturas y su luz), no la losa del 4 con otra textura
            libres = dict(paneles)
            con_panel = 0
            for k, o in enumerate(lista):
                if o["tipo"] not in ("secreta", "puerta") or not libres:
                    continue
                pk = min(libres, key=lambda q: (q[0] - o["pos"][0]) ** 2 + (q[1] - o["pos"][1]) ** 2)
                if (pk[0] - o["pos"][0]) ** 2 + (pk[1] - o["pos"][1]) ** 2 < 2.0 ** 2:
                    lista[k] = dict(o, tipo="secreta", panel=libres.pop(pk), es_puerta=o["tipo"] == "puerta")
                    con_panel += 1
            log.append(f"Paredes secretas y puertas con su modelo del King's Field: {con_panel} de {len(paneles)}")
        puerta_kf = getattr(valle, "kf_puerta_en", None)
        if puerta_kf and OBJ_SECRETA in plantillas_obj:
            # las puertas del King's Field suben al abrirse, como la losa del 4: la losa con la textura de la puerta
            # (la puerta del 4 era una reja)
            cambiadas = 0
            for k, o in enumerate(lista):
                if o["tipo"] == "puerta":
                    t = puerta_kf(o["pos"])
                    if t:
                        lista[k] = dict(o, tipo="secreta", tex_kf=t)
                        cambiadas += 1
            if cambiadas:
                log.append(f"Puertas del King's Field con su textura: {cambiadas}")
        objs, obj_secc, extra = colocar_objetos_kf(objs, obj_secc, lista, plantillas_obj, recs, log, muro)
        nobj += extra
    if obj_secc and getattr(valle, "kf_fuentes", None):
        objs, extra = fuentes_que_curan(h, objs, valle.kf_fuentes, recs, log)
        nobj += extra

    # cabecera y bloques de niebla / luz / texturas animadas de 031
    head = bytearray(h[:0x80])
    blocks = bytearray(d031[0x80:md.OFF_RECORDS])
    fogcol = niebla[0] | (niebla[1] << 8) | (niebla[2] << 16)
    for i in range(32):
        o = i * 0x20
        struct.pack_into("<4f", blocks, o, 0.0, 0.0, -12.0, niebla_k)
        struct.pack_into("<Q", blocks, o + 0x10, fogcol)

    # bloque de luz de los enemigos: luna fría desde arriba, relleno cálido, ambiente suficiente
    lb = LUZ_ENEMIGOS * 0x80 + 0x400
    dirs = [(0.25, 0.85, 0.45), (-0.6, -0.3, 0.7), (0.0, -1.0, 0.0)]   # (x, y, z) del juego, Y hacia abajo
    for ax in range(4):
        for li in range(4):
            v = dirs[li][ax] if (li < 3 and ax < 3) else (1.0 if (ax == 3 and li == 3) else 0.0)
            struct.pack_into("<f", blocks, lb + (ax * 4 + li) * 4, v)
    for li, col in enumerate([(0.55, 0.60, 0.70, 0.0), (0.45, 0.32, 0.18, 0.0), (0.10, 0.10, 0.12, 0.0),
                              (0.42, 0.42, 0.46, 1.0)]):
        struct.pack_into("<4f", blocks, lb + 0x40 + li * 16, *col)
    lb = LUZ_OBJETOS_KF * 0x80 + 0x400
    for ax in range(4):
        for li in range(4):
            v = dirs[li][ax] if (li < 3 and ax < 3) else (1.0 if (ax == 3 and li == 3) else 0.0)
            struct.pack_into("<f", blocks, lb + (ax * 4 + li) * 4, v)
    for li, col in enumerate(LUZ_OBJETOS_KF_COLORES):
        struct.pack_into("<4f", blocks, lb + 0x40 + li * 16, *col)
    lb = LUZ_PANEL * 0x80 + 0x400
    for ax in range(4):
        for li in range(4):
            v = dirs[li][ax] if (li < 3 and ax < 3) else (1.0 if (ax == 3 and li == 3) else 0.0)
            struct.pack_into("<f", blocks, lb + (ax * 4 + li) * 4, v)
    # (estimado de 3 capturas, no comprobado: los objetos parecen dar textura x color/64 x luz, con tope en 1, y el
    # mapa textura x color/128:
    # con 0,5 los dos casan si la pared lleva los colores de vértice de las de al lado)
    for li, col in enumerate([(0.0, 0.0, 0.0, 0.0)] * 3 + [(LUZ_PANEL_AMB,) * 3 + (1.0,)]):
        struct.pack_into("<4f", blocks, lb + 0x40 + li * 16, *col)

    if cielo:
        # las nubes del 4: 099 compone la textura del cielo (0x3A80) cada fotograma con tres capas de nubes que se
        # desplazan (tabla de texturas animadas en 0x1480; las capas están en sus paquetes 2 y 4)
        if "nubes" not in QUITAR:
            blocks[OFF_ANIM:OFF_ANIM + 0x340] = d099[0x1480:0x17C0]
    atlas = getattr(valle, "kf_atlas", None)
    if atlas is not None and getattr(atlas, "agua", None) is not None and "agua" not in QUITAR:
        poner_agua_animada(blocks, log)
    if cielo:      # niebla y luz del cielo: las del registro 0 de 099 (bloque 3: sin niebla)
        blocks[CIELO_FOG * 0x20:(CIELO_FOG + 1) * 0x20] = d099[0x80 + 3 * 0x20:0x80 + 4 * 0x20]
        lo = 0x400 + CIELO_LUZ * 0x80
        blocks[lo:lo + 0x80] = d099[0x480 + 3 * 0x80:0x480 + 4 * 0x80]
    rec_bytes = bytearray()
    for r in recs:
        if "raw" in r:
            b = bytearray(r["raw"])
            ox, oy, oz = r["origin"]
            struct.pack_into("<3f", b, 0x00, ox, oy, oz)
            struct.pack_into("<hh", b, 0x30, r["omd"], -1)
            b[0x34] = CIELO_FOG
            b[0x35] = CIELO_LUZ
            b[0x38] = 1          # el bloque de flags de los demás registros (el 8 de 099 depende del guion)
            for base in (0x40, 0x50):
                x, y, z = struct.unpack_from("<3f", b, base)
                struct.pack_into("<3f", b, base, x + ox, y + oy, z + oz)
            rec_bytes += b
            continue
        b = bytearray(md.REC)
        struct.pack_into("<4f", b, 0x00, r["origin"][0], r["origin"][1], r["origin"][2], 0.0)
        struct.pack_into("<4f", b, 0x10, 0, 0, 0, 0)
        struct.pack_into("<4f", b, 0x20, 1, 1, 1, 0)
        struct.pack_into("<hh", b, 0x30, r["omd"], r["csk"])
        b[0x34] = 0      # niebla
        b[0x35] = 6      # luz (la de la roca en 031)
        b[0x36] = 0      # niebla de los enemigos que lo pisan
        b[0x37] = LUZ_ENEMIGOS
        b[0x38] = 1      # bloque de flags
        b[0x39] = 0
        b[0x3A] = 0xFF   # sin vecino que precargar
        b[0x3B] = 0
        struct.pack_into("<I", b, 0x3C, 5 if r.get("tarde") else 4)
        if "box" in r:
            (a0, a1, a2), (b0, b1, b2) = r["box"]
            struct.pack_into("<4f", b, 0x40, a0, a1, a2, 0)
            struct.pack_into("<4f", b, 0x50, b0, b1, b2, 0)
        if "cbox" in r:
            (a0, a1, a2), (b0, b1, b2) = r["cbox"]
            struct.pack_into("<4f", b, 0x60, a0, a1, a2, 0)
            struct.pack_into("<3f", b, 0x70, b0, b1, b2)
        rec_bytes += b

    # las tablas tienen que caber antes de los modelos, en el hueco de 099 (0x5FB0): si los modelos se corren, el
    # juego se cuelga al cargar el mapa (probado: el 7 sin enemigos cabe y va; con ellos no cabe y se cuelga).
    # Si no caben se quitan, por este orden: enemigos (repartidos), paredes / puertas / cofres portados (del
    # final de la lista) y objetos del suelo.
    fijo = len(head) + len(blocks) + len(rec_bytes) + len(flag_blocks) + len(neigh) + len(tabla_tipos) + len(umbrales)
    nobj0 = struct.unpack_from("<5H", h, 0x3C)[2]
    quitados = collections.Counter()
    # (antes se quitaban enemigos y objetos para que las tablas cupieran en el hueco de 099; el cuelgue que parecía
    # venir de ahí era el banco de sonido mal apuntado: ahora los modelos se corren y cabe todo)
    while RECORTAR_TABLAS and fijo + len(objs) + len(spawns) + len(items) > off_models:
        sobra = fijo + len(objs) + len(spawns) + len(items) - off_models
        if nsp > 16:
            n = max(1, min(nsp - 16, -(-sobra // md.SPAWNREC)))
            quedan = nsp - n
            spawns = b"".join(bytes(spawns[(i * nsp // quedan) * md.SPAWNREC:(i * nsp // quedan + 1) * md.SPAWNREC])
                              for i in range(quedan))
            spawns = bytearray(spawns)
            for i in range(quedan):
                spawns[i * md.SPAWNREC + 0x3C] = i & 0xFF
            nsp = quedan
            quitados["enemigos"] += n
        elif nobj > nobj0:
            objs = bytes(objs)[:-md.OBJREC]
            nobj -= 1
            quitados["objetos portados"] += 1
        elif nit > 0:
            items = bytes(items)[:-md.ITEMREC]
            nit -= 1
            quitados["objetos del suelo"] += 1
        elif nsp > 0:
            spawns = bytes(spawns)[:-md.SPAWNREC]
            nsp -= 1
            quitados["enemigos"] += 1
        else:
            break
    if quitados:
        log.append("AVISO: no cabía todo en las tablas del mapa (hueco de 099); quitados: "
                   + ", ".join(f"{n} {t}" for t, n in quitados.items()))
    tables = (bytes(head) + bytes(blocks) + bytes(rec_bytes) + flag_blocks + neigh + bytes(objs) + bytes(spawns)
              + bytes(items) + tabla_tipos + umbrales)
    # los modelos empiezan donde diga la cabecera (0x04): cada mapa original tiene sus tablas de un tamaño, así
    # que si no caben en el hueco de 099 se corren los modelos (y con ellos todo lo demás)
    if len(tables) > off_models:
        log.append(f"AVISO: tablas de {len(tables)} bytes (el hueco de 099 es de {off_models}): se corren los modelos")
    new_models = max(off_models, (len(tables) + 15) // 16 * 16)
    tables += bytes(new_models - len(tables))

    out = bytearray(tables)
    out += omd_blob + bytes(max(0, room_m - len(omd_blob)))
    new_coll = len(out)
    seccion = bytearray(csk_blob)
    if bloque_cruz:
        # las fuentes que curan del mapa portado (la WaterWell del King's Field): en el espacio del juego
        import kf4_cruz
        # las fuentes curan con el guion del propio juego (fuentes_que_curan): la cura del código, apagada
        bloque_cruz = kf4_cruz.poner_fuentes(bloque_cruz, [])
        # las ilustraciones de la cruz van detrás de la colisión (el motor no lee esa parte), alineadas a 16
        seccion += bytes((-(len(out) + len(seccion))) % 16)
        seccion += bloque_cruz
    if RELLENO:          # prueba: bytes de más donde el motor no lee, para ver si un mapa grande cuelga el juego
        seccion += bytes((-(len(out) + len(seccion))) % 16) + bytes(RELLENO)
        log.append(f"PRUEBA: {RELLENO // 1024} KB de relleno")
    out += seccion + bytes(max(0, room_c - len(seccion)))
    delta = len(out) - off_objm
    off_item = struct.unpack_from("<I", h, 0x20)[0]
    off_script = struct.unpack_from("<I", h, 0x4C)[0]
    if obj_secc:
        new_obj = []
        for blob in obj_secc[1]:
            new_obj.append(len(out))
            out += blob
    else:
        out += h[off_objm:off_item]
    new_item = len(out)
    out += item_blob
    new_script = len(out)
    guion = h[off_script:off_tex]
    if getattr(valle, "kf_fuentes", None):
        guion = guion_fuente(guion, d099, log)
    guion = guion_paneles(guion, log)
    out += guion
    new_tex = len(out)
    if getattr(valle, "kf_atlas", None) is not None:   # geometría real de King's Field: su atlas de texturas
        import kf_malla
        tex_blob = kf_malla.inyectar(tex_blob, valle.kf_atlas, log)
        n_reg, sin_sitio, tris_kf = valle.kf_info
        log.append(f"Decorado del King's Field: {getattr(valle, 'kf_props', 0)} objetos (barriles, mesas, tumbas...)"
                   f" y {len(getattr(valle, 'kf_fuentes', []))} fuentes que curan")
        if sin_sitio:
            log.append(f"AVISO: {sin_sitio} polígonos sin sitio en el atlas de texturas (no se dibujan)")
    elif getattr(valle, "texturas_kf2", None):          # texturas de King's Field II en los huecos del editor
        import kf2_tex
        import kf4_tex as kt
        a_, b_ = struct.unpack_from("<II", d099, 0x24)
        texs, _, _ = kt.load_map_textures(d099)
        fs = {(f["TBP"], f["CBP"]): f for f, _ in texs.values()}
        cambios = {}
        for (tbp, cbp), img in valle.texturas_kf2.items():
            f = fs.get((tbp, cbp))
            if f and f["PSM"] == 0x14 and bytes(tex_blob) == bytes(d099[a_:b_]):
                cambios[(tbp, cbp, f["TBW"], f["W"], f["H"])] = img
        if cambios:
            tex_blob = kf2_tex.inyectar(tex_blob, cambios, log)
    out += tex_blob
    new_snd = len(out)
    out += h[off_snd:]
    # el banco de sonido guarda dos offsets desde el principio del fichero (+4 buffer_b, +0xC buffer_a; Map_ParseFile
    # les suma la base): si el banco se mueve hay que moverlos con él. Sin esto el mapa carga basura como banco de
    # sonido y el primer banco de un enemigo no termina nunca de cargar: pantalla negra con cualquier enemigo.
    mov_snd = new_snd - off_snd
    for o in (4, 0xC):
        v = struct.unpack_from("<I", out, new_snd + o)[0]
        struct.pack_into("<I", out, new_snd + o, v + mov_snd)
    log.append(f"Banco de sonido en {new_snd:#x} (movido {mov_snd:+d} bytes; punteros internos corregidos)")
    # cabecera: offsets de las secciones movidas
    struct.pack_into("<I", out, 0x00, len(out))
    struct.pack_into("<I", out, 0x04, new_models)
    struct.pack_into("<I", out, 0x08, new_coll)
    if obj_secc:
        for o, v in zip((0x0C, 0x10, 0x14, 0x18), new_obj):
            struct.pack_into("<I", out, o, v)
        struct.pack_into("<4H", out, 0x30, *obj_secc[0])
    else:
        for o in (0x0C, 0x10, 0x14, 0x18):
            v = struct.unpack_from("<I", h, o)[0]
            if v:
                struct.pack_into("<I", out, o, v + delta)
    struct.pack_into("<I", out, 0x20, new_item)
    struct.pack_into("<I", out, 0x4C, new_script)
    struct.pack_into("<I", out, 0x24, new_tex)
    struct.pack_into("<I", out, 0x28, new_snd)
    if delta:
        log.append(f"Secciones de 099 desplazadas {delta} bytes para que quepa la geometría")
    struct.pack_into("<HH", out, 0x2C, len(omds), len(csks))
    struct.pack_into("<H", out, 0x3C, len(recs))
    struct.pack_into("<H", out, 0x40, nobj)
    struct.pack_into("<H", out, 0x42, nsp)
    struct.pack_into("<H", out, 0x44, nit)
    struct.pack_into("<H", out, 0x3A, len(kinds))
    out[0x50:0x53] = bytes(niebla)
    sx, sy, sz = to_native(valle.inicio)
    rumbo = getattr(valle, "rumbo", rumbo)
    struct.pack_into("<4f", out, 0x60, sx, sy, sz, rumbo)
    patch_intro_script(out, valle, log)
    out[0x70] = d031[0x70]          # música de los acantilados
    out[0x78:0x7C] = bytes(4)
    out[0x71] = LUZ_ENEMIGOS        # bloque de luz de los objetos del suelo (el de 099 está vacío aquí: salían negros)
    if getattr(valle, "kf_atlas", None) is not None and "recorte" not in QUITAR:
        out = recortar_texturas(out, log)
    log.append(f"Tamaño final 099.map: {len(out)} bytes (original {len(h)})")
    # el mapa se lee en map_file_area, de 0xA80000 bytes (core/memory.c); si no cabe pisa la memoria de detrás
    if len(out) > MAPA_MAXIMO:
        log.append(f"(el mapa pasa de {MAPA_MAXIMO} bytes, lo que se deja cargar: se intenta aligerar)")
    log.append(f"Inicio del jugador (juego): {sx:.0f} {sy:.0f} {sz:.0f} rumbo {rumbo}")
    return bytes(out), stats


# ======================= Parche de la ISO =======================
CMD_MOVE_PLAYER_TO = 120
CMD_TURN_PLAYER_TO = 121
ARG_FLOAT = 0x60000


def patch_intro_script(out, valle, log):
    """El script de 099 lleva la intro de Partida nueva, que mueve al jugador a la puerta del
    Palacio de Oath (fuera del valle: caía al vacío). Se reescriben sus MovePlayerTo/TurnPlayerTo para
    que la intro ocurra en la cornisa, mirando a lo largo del valle (rumbo 0 = hacia +Y)."""
    so = struct.unpack_from("<I", out, 0x4C)[0]
    end = struct.unpack_from("<I", out, 0x24)[0]
    i = so
    moves = turns = 0
    while i + 4 <= end:
        w = struct.unpack_from("<I", out, i)[0]
        op, t = w & 0xFFFF, w >> 16
        if t == 0x190:
            if op == 0x7FFE:
                break
            i += 4
        elif t in (0x191, 0x194, 0x195, 0x197):
            i += 4
        elif t == 0x192:
            i += 4 * (1 + (op >> 8) * 5 + 1)
        elif t == 0x196:
            i += 4 * (1 + op)
        elif t == 0x19D:
            i += 4 * (1 + op + 1)
        else:
            if t == CMD_MOVE_PLAYER_TO and op >= 3 and moves < len(valle.intro):
                x, y, z = to_native(valle.intro[moves])
                for k, v in enumerate((x, y, z)):
                    struct.pack_into("<If", out, i + 4 + k * 8, ARG_FLOAT, v)
                moves += 1
            elif t == CMD_TURN_PLAYER_TO and op >= 2:
                struct.pack_into("<If", out, i + 4 + 8, ARG_FLOAT, getattr(valle, "rumbo", 0.0))
                turns += 1
            i += 4 * (1 + op * 2)
    log.append(f"Intro de Partida nueva recolocada en el valle ({moves} movimientos, {turns} giros)")
    if moves == 0:
        log.append("AVISO: no encontré la intro en el script de 099")


def _dat_table(path, lang):
    """{nombre: (posición del registro en la ISO, tamaño, hueco, offset)} del DAT de ese idioma."""
    try:
        s = md.Source(path, lang)
    except RuntimeError:
        return None, None
    if not s.dat.endswith(f"_{lang}.DAT"):
        return None, None
    out = {}
    with open(path, "rb") as f:
        f.seek(s.dat_off)
        count = struct.unpack_from("<I", f.read(0x40), 4)[0]
        table = f.read(count * 0x40)
    for i in range(count):
        r = table[i * 0x40:(i + 1) * 0x40]
        nm = r[:0x34].split(b"\x00", 1)[0].decode("ascii", "replace").lower()
        out[nm] = (s.dat_off + 0x40 + i * 0x40, *struct.unpack_from("<III", r, 0x34))
    return s.dat_off, out


# ======================= Parches del ejecutable (SLES_509.20, PAL) =======================
# Tablas de giro del jugador (player_update.c en kfiv-decomp; en PAL están en el mismo orden):
#   velocidad máxima de giro [6], ganancia por fotograma [12], pérdida por fotograma [6] (rad/fotograma)
GIRO_TOP = [0.029088821, 0.029088821, 0.019392548, 0.014544411, 0.014544411, 0.0]
GIRO_GAIN = [0.0029088822, 0.0029088822, 0.0019392548, 0.0014544411, 0.0014544411, 0.0] * 2
GIRO_LOSS = [0.0026179939, 0.0026179939, 0.0026179939, 0.0013089969, 0.0026179939, 0.0]


# ======================= Mando: dos sticks (parche del ejecutable) =======================
# Input_ReadPort (kfiv-decomp, input/input.c) convierte los sticks en botones digitales:
#   stick izquierdo = cruceta (adelante/atrás y GIRAR), stick derecho Y = L2/R2, stick derecho X = nada.
# Se reescribe la función en su mismo sitio para que sea como un juego moderno:
#   stick izquierdo Y = adelante/atrás, stick izquierdo X = paso lateral (L1/R1),
#   stick derecho X = girar, stick derecho Y = mirar arriba/abajo.
PAD_IZQ, PAD_DER, PAD_ARR, PAD_ABA = 0x80, 0x20, 0x10, 0x40
PAD_L2, PAD_R2, PAD_L1, PAD_R1 = 0x100, 0x200, 0x400, 0x800
_R = {"zero": 0, "v0": 2, "v1": 3, "a0": 4, "a1": 5, "a2": 6, "a3": 7, "t0": 8, "t1": 9, "t2": 10,
      "t3": 11, "t4": 12, "t5": 13, "t6": 14, "t7": 15, "s0": 16, "s1": 17, "s2": 18, "s3": 19, "s4": 20,
      "s5": 21, "s6": 22, "s7": 23, "t8": 24, "t9": 25, "sp": 29, "ra": 31}
_I = {"addiu": 0x09, "slti": 0x0A, "sltiu": 0x0B, "lh": 0x21, "sb": 0x28, "andi": 0x0C, "ori": 0x0D, "lui": 0x0F, "lbu": 0x24, "lhu": 0x25,
      "lw": 0x23, "sh": 0x29, "sw": 0x2B, "sd": 0x3F, "ld": 0x37}
_F = {"addu": 0x21, "subu": 0x23, "and": 0x24, "or": 0x25, "nor": 0x27, "slt": 0x2A, "move": 0x2D}


def _ensamblar(prog, base):
    """Mini ensamblador MIPS (solo lo que usa este parche). prog: lista de tuplas; 'etiqueta:' marca."""
    pos, n = {}, 0
    for ins in prog:
        if isinstance(ins, str):
            pos[ins] = base + n * 4
        else:
            n += 1
    out, pc = [], base
    for ins in prog:
        if isinstance(ins, str):
            continue
        op, *a = ins
        if op in _I:
            if op in ("lbu", "lhu", "lh", "lw", "sb", "sh", "sw", "sd", "ld"):      # rt, imm(rs)
                rt, imm, rs = a
            elif op == "lui":
                rt, imm, rs = a[0], a[1], "zero"
            else:                                                     # rt, rs, imm
                rt, rs, imm = a
            w = (_I[op] << 26) | (_R[rs] << 21) | (_R[rt] << 16) | (imm & 0xFFFF)
        elif op in _F:
            rd, rs, rt = (a[0], a[1], "zero") if op == "move" else a
            w = (_R[rs] << 21) | (_R[rt] << 16) | (_R[rd] << 11) | _F[op]
        elif op in ("sll", "srl", "sra"):
            rd, rt, sa = a
            w = (_R[rt] << 16) | (_R[rd] << 11) | (sa << 6) | {"sll": 0, "srl": 2, "sra": 3}[op]
        elif op == "srlv":                                            # rd = rt >> rs
            rd, rt, rs = a
            w = (_R[rs] << 21) | (_R[rt] << 16) | (_R[rd] << 11) | 0x06
        elif op in ("mult", "div"):
            rs, rt = a
            w = (_R[rs] << 21) | (_R[rt] << 16) | (0x18 if op == "mult" else 0x1A)
        elif op in ("mflo", "mfhi"):
            w = (_R[a[0]] << 11) | (0x12 if op == "mflo" else 0x10)
        elif op in ("beq", "bne"):
            rs, rt, lab = a
            off = (pos[lab] - (pc + 4)) >> 2
            w = ((4 if op == "beq" else 5) << 26) | (_R[rs] << 21) | (_R[rt] << 16) | (off & 0xFFFF)
        elif op == "jal":
            dest = pos[a[0]] if isinstance(a[0], str) else a[0]
            w = (3 << 26) | ((dest >> 2) & 0x3FFFFFF)
        elif op == "j":
            dest = pos[a[0]] if isinstance(a[0], str) else a[0]
            w = (2 << 26) | ((dest >> 2) & 0x3FFFFFF)
        elif op == "jr":
            w = (_R[a[0]] << 21) | 0x08
        elif op == "nop":
            w = 0
        elif op == "lwc1":                                            # ("lwc1", "f3", off, "t1")
            ft, imm, rs = a
            w = (0x31 << 26) | (_R[rs] << 21) | (int(ft[1:]) << 16) | (imm & 0xFFFF)
        elif op in ("add.s", "sub.s", "mul.s"):                       # fd, fs, ft
            fd, fs, ft = (int(r[1:]) for r in a)
            w = 0x46000000 | (ft << 16) | (fs << 11) | (fd << 6) | {"add.s": 0, "sub.s": 1, "mul.s": 2}[op]
        elif op == "c.lt.s":                                          # fs, ft
            fs, ft = (int(r[1:]) for r in a)
            w = 0x46000034 | (ft << 16) | (fs << 11)
        elif op in ("bc1t", "bc1f"):
            off = (pos[a[0]] - (pc + 4)) >> 2
            w = (0x45010000 if op == "bc1t" else 0x45000000) | (off & 0xFFFF)
        else:
            raise ValueError(op)
        out.append(w)
        pc += 4
    return b"".join(w.to_bytes(4, "little") for w in out)


def _eje(off, reg, bajo, alto):
    """reg |= bajo si el eje < 0x40; reg |= alto si el eje > 0xC0 (sin saltos)."""
    return [("lbu", "v1", off, "a2"),
            ("sltiu", "v0", "v1", 0x40), ("subu", "v0", "zero", "v0"), ("andi", "v0", "v0", bajo),
            ("or", reg, reg, "v0"),
            ("sltiu", "v0", "v1", 0xC1), ("addiu", "v0", "v0", -1), ("andi", "v0", "v0", alto),
            ("or", reg, reg, "v0")]


def _grupo(reg, off):
    """Guarda los botones del stick (off) y los del fotograma anterior (off+2), y los suma a
    held/pressed del mando (pressed solo los que se acaban de pulsar)."""
    return [("lhu", "v0", off, "s0"), ("sh", "v0", off + 2, "s0"), ("sh", reg, off, "s0"),
            ("nor", "v0", "zero", "v0"), ("and", "v0", reg, "v0"),
            ("lhu", "v1", 0, "s0"), ("or", "v1", "v1", reg), ("sh", "v1", 0, "s0"),
            ("lhu", "a0", 2, "s0"), ("or", "a0", "a0", "v0"), ("sh", "a0", 2, "s0")]


# Escalón del jugador: Player_CollideWithMap (player_collision.c) busca el suelo desde 75 cm por encima de los
# pies (floor_point.y -= 75; reach = fall_speed + 75), así que no sube nada más alto. Los escalones del King's
# Field son de 0,78 m: se cambia ese 75.0 por 100.0. En el US está en 0x1BDDC0 (0x9A0 bytes); en el PAL las
# funciones de esa zona están 0x17E0 antes (Input_ReadPort: 0x1B5590 -> 0x1B3DB0). Se busca el "lui rX, 0x4296"
# (la parte alta de 75.0) en esa ventana.
ESCALON_VENTANA = (0x1BC5E0 - 0x400, 0x1BC5E0 + 0x9A0 + 0x400)
GP_EJECUTABLE = 0x453870
SUBIDA_GOLPE_CM = 75.0
ESCALON_CM = 130.0      # los escalones de casilla del King's Field son de 1,25 m y allí se suben


def parche_escalon(e, log):
    a, b = (v - 0xFF000 for v in ESCALON_VENTANA)
    nuevo = struct.unpack("<I", struct.pack("<f", ESCALON_CM))[0] >> 16
    sitios = []
    for o in range(a, min(b, len(e) - 4), 4):
        w = struct.unpack_from("<I", e, o)[0]
        if (w & 0xFFE0FFFF) == 0x3C004296:          # lui rt, 0x4296 (rs = 0)
            rt = (w >> 16) & 0x1F
            # que se use como float: un mtc1 rt, fN en las 6 instrucciones siguientes
            for k in range(1, 7):
                w2 = struct.unpack_from("<I", e, o + 4 * k)[0]
                if (w2 & 0xFFFF07FF) == (0x44800000 | (rt << 16)):
                    sitios.append(o)
                    break
    if 1 <= len(sitios) <= 3:
        for o in sitios:
            w = struct.unpack_from("<I", e, o)[0]
            struct.pack_into("<I", e, o, (w & 0xFFFF0000) | nuevo)
        log.append(f"Escalón del jugador: sube {ESCALON_CM:.0f} cm (antes 75; {len(sitios)} sitios en "
                   f"Player_CollideWithMap)")
    else:
        log.append(f"AVISO: no encontré el 75.0 del escalón del jugador ({len(sitios)} candidatos); sin cambiar")
    # PLAYER_STEP_HEIGHT (16,67 cm): lo que sube de golpe; si el suelo está más alto entra en "subiendo" y sube
    # 16,67 cm por fotograma SIN mirar el suelo. Corriendo (o con el dash) por una escalera de 45 grados se avanza
    # más deprisa de lo que sube, y al acabar el suelo ya queda por encima de lo que busca: se cae a través de la
    # escalera. Con 75 cm sube de golpe todo lo que encuentra.
    viejo_hi, viejo_lo = 0x4185, 0x5555
    nuevo_f = struct.unpack("<I", struct.pack("<f", SUBIDA_GOLPE_CM))[0]
    hechos = 0
    for o in range(a, min(b, len(e) - 8), 4):
        w = struct.unpack_from("<I", e, o)[0]
        if (w & 0xFFE0FFFF) == (0x3C000000 | viejo_hi):
            rt = (w >> 16) & 0x1F
            for k in range(1, 4):
                w2 = struct.unpack_from("<I", e, o + 4 * k)[0]
                if (w2 >> 26) == 0x0D and ((w2 >> 21) & 0x1F) == rt and ((w2 >> 16) & 0x1F) == rt \
                        and (w2 & 0xFFFF) == viejo_lo:
                    struct.pack_into("<I", e, o, (w & 0xFFFF0000) | (nuevo_f >> 16))
                    struct.pack_into("<I", e, o + 4 * k, (w2 & 0xFFFF0000) | (nuevo_f & 0xFFFF))
                    hechos += 1
                    break
    if not hechos:
        # en el SLES_509.20 el 16,67 no va en instrucciones: se lee de la reserva de constantes con lwc1 fN, off(gp)
        # (gp = 0x453870, de la entrada del ejecutable); se cambian las palabras que leen esas lwc1 de la ventana
        viejo = struct.pack("<f", 16.666666)
        vistos = set()
        for o in range(a, min(b, len(e) - 4), 4):
            w = struct.unpack_from("<I", e, o)[0]
            if (w >> 26) == 0x31 and ((w >> 21) & 0x1F) == 28:
                dest = GP_EJECUTABLE + struct.unpack("<h", struct.pack("<H", w & 0xFFFF))[0] - 0xFF000
                if 0 <= dest < len(e) - 4 and bytes(e[dest:dest + 4]) == viejo and dest not in vistos:
                    vistos.add(dest)
        if 1 <= len(vistos) <= 4:
            for dest in vistos:
                struct.pack_into("<f", e, dest, SUBIDA_GOLPE_CM)
            hechos = len(vistos)
    if hechos:
        log.append(f"Subida de golpe del jugador: {SUBIDA_GOLPE_CM:.0f} cm (antes 16,7; {hechos} sitios): no se cuela "
                   f"en las escaleras al correr")
    else:
        log.append("AVISO: no encontré los 16,67 cm de subida del jugador; corriendo por escaleras empinadas se cuela")


LEER_MANDO_VA = 0x1B3DB0          # Input_ReadPort en SLES_509.20
LEER_MANDO_FIN = 0x1B3F94
LEER_MANDO_FIRMA = bytes.fromhex("d0ffbd27 4100023c 1000b1ff 78354224".replace(" ", ""))


def codigo_mando(invertir_mirar=False, cruz=False):
    mirar_arr, mirar_aba = (PAD_L2, PAD_R2) if not invertir_mirar else (PAD_R2, PAD_L2)
    # stick arriba (< 0x40) = mirar arriba (con el stick original arriba bajaba la vista)
    prog = [("addiu", "sp", "sp", -0x30), ("lui", "v0", 0x41), ("sd", "s1", 0x10, "sp"),
            ("addiu", "v0", "v0", 0x3578), ("move", "s1", "a0"), ("sd", "s0", 0, "sp"),
            ("sll", "v1", "s1", 4), ("sd", "ra", 0x20, "sp"), ("addu", "s0", "v1", "v0"),
            ("jal", 0x216260), ("move", "a1", "zero"),                       # Pad_GetMode(port, 0)
            ("addiu", "v1", "zero", 0xFF), ("beq", "v0", "v1", "sin_mando"), ("sw", "v0", 4, "s0"),
            ("move", "a0", "s1"), ("jal", 0x215FC8), ("move", "a1", "zero"),  # Pad_GetReport(port, 0)
            ("move", "a2", "v0"), ("lw", "a3", 4, "s0"),
            ("lhu", "v0", 2, "a2"), ("sh", "v0", 0, "s0"),                    # held
            ("lhu", "v1", 0x20, "a2"), ("sh", "v1", 2, "s0"),                 # pressed
            ("addiu", "a0", "zero", 1), ("bne", "a3", "a0", "sin_analog"), ("nop",)]
    if cruz:
        # la cruceta no anda: se quita de los botones y se guarda para la cruz de equipo
        ch_, cl_ = _hi_lo(CRUZ_PULSADO)
        prog += [("lhu", "v0", 0, "s0"), ("andi", "v0", "v0", 0xFF0F), ("sh", "v0", 0, "s0"),
                 ("lhu", "v1", 2, "s0"), ("andi", "t2", "v1", 0x00F0), ("andi", "v1", "v1", 0xFF0F), ("sh", "v1", 2, "s0"),
                 ("lui", "t3", ch_), ("lhu", "t4", cl_, "t3"), ("or", "t4", "t4", "t2"), ("sh", "t4", cl_, "t3")]
    prog += [
            ("move", "t0", "zero"), ("move", "t1", "zero")]
    prog += _eje(4, "t0", PAD_IZQ, PAD_DER)            # stick derecho X: girar
    prog += _eje(5, "t0", mirar_arr, mirar_aba)        # stick derecho Y: mirar
    prog += _eje(6, "t1", PAD_L1, PAD_R1)              # stick izquierdo X: paso lateral
    prog += _eje(7, "t1", PAD_ARR, PAD_ABA)            # stick izquierdo Y: andar
    prog += _grupo("t0", 8) + _grupo("t1", 0xC)
    prog += ["fin", ("ld", "ra", 0x20, "sp"), ("ld", "s1", 0x10, "sp"), ("ld", "s0", 0, "sp"),
             ("jr", "ra"), ("addiu", "sp", "sp", 0x30),
             "sin_mando", ("sh", "zero", 0, "s0"), ("sh", "zero", 2, "s0"),
             "sin_analog", ("sh", "zero", 8, "s0"), ("sh", "zero", 0xA, "s0"),
             ("sh", "zero", 0xC, "s0"), ("beq", "zero", "zero", "fin"), ("sh", "zero", 0xE, "s0")]
    code = _ensamblar(prog, LEER_MANDO_VA)
    hueco = LEER_MANDO_FIN - LEER_MANDO_VA
    assert len(code) <= hueco, len(code)
    return code + bytes(hueco - len(code))


# ======================= HUD: vida en número dentro del orbe (parche del ejecutable) =======================
# Hud_Draw (kfiv-decomp, ui/hud.c) dibuja el marco y las barras. Su última llamada (el brillo del orbe,
# GsDraw_QueueTexturedSprite) se desvía a una rutina nueva que, después de hacer esa misma llamada, escribe
# "vida/máxima" (player_state.hp_now / hp_max) con una fuente de píxeles propia, en rectángulos planos
# (GsDraw_QueueFlatSprite), centrada en el orbe rojo y con sombra. La rutina vive donde estaban
# Debug_EditU16/EditU8/EditFloat, que nada llama.
VIDA_HUECO_VA, VIDA_HUECO_FIN = 0x1AED10, 0x1AF170
VIDA_HUECO_FIRMA = bytes.fromhex("10a6888fffffa530ffffc630ffffe730")
VIDA_GANCHO_VA = 0x1D0818                       # jal GsDraw_QueueTexturedSprite (sprite 9) en Hud_Draw
VIDA_GANCHO_ORIG = (3 << 26) | (0x109050 >> 2)
SPRITE_TEXTURADO, SPRITE_PLANO = 0x109050, 0x109288
PLAYER_STATE = 0x413740
HP_AHORA = PLAYER_STATE + 0xB4                  # player_state.hp_now
HP_MAX = PLAYER_STATE + 0x58                    # player_state.hp_max
ORBE = 0x5D4A58 + 3 * 0x40                      # hud_sprites[3]: el relleno rojo del orbe
# Fuente: Windi Script B (goburinbro, CC0), cifras de 7 x 9, cada fila una línea de pantalla (su proporción de
# verdad). Avance de 9 píxeles por carácter: un píxel de aire entre cifras.
FUENTE = {
    "0": ["..####.", ".##..##", ".##..##", "##..###", "##.#.##", "###..##", "##..##.", "##..##.", ".####.."],
    "1": ["....##.", "..####.", "....##.", "...##..", "...##..", "...##..", "..##...", "..##...", "######."],
    "2": ["..####.", ".##..##", ".##..##", "....##.", "..###..", ".##....", "##.....", "##..##.", "######."],
    "3": ["..####.", ".##..##", ".##..##", "....##.", "..###..", "....##.", "##..##.", "##..##.", ".####.."],
    "4": ["....###", "...####", "..##.##", ".##.##.", "##..##.", "#######", "...##..", "...##..", "..####."],
    "5": ["..#####", "..##...", ".##....", ".#####.", ".##..##", ".....##", "##...##", "##..##.", ".####.."],
    "6": ["...##..", "...##..", "..##...", "..####.", ".##..##", "##...##", "##...##", "##..##.", ".####.."],
    "7": ["######.", "##..##.", "...##..", "..##...", "..##...", ".##....", ".##....", "##.....", "##....."],
    "8": ["...###.", "..##.##", ".##..##", ".##.##.", "..###..", ".##..##", "##...##", "##..##.", ".####.."],
    "9": ["..####.", ".##..##", "##...##", "##...##", "##..##.", ".####..", "...##..", "..##...", "..##..."],
    "/": [".....##", ".....##", "....##.", "....##.", "...##..", "..##...", "..##...", ".##....", ".##...."],
}
FUENTE_WINDI = FUENTE
# Fuente propia de trazo fino de 1 píxel, ancha y geométrica, con el cero tachado (al estilo de los números de
# menú de los juegos de rol de PS1). Es la que se usa; FUENTE_WINDI queda por si se quiere volver.
FUENTE_FINA = {
    "0": [".#####.", "#.....#", "#....##", "#...#.#", "#..#..#", "#.#...#", "##....#", "#.....#", ".#####."],
    "1": ["...#...", "..##...", ".#.#...", "...#...", "...#...", "...#...", "...#...", "...#...", ".#####."],
    "2": [".#####.", "#.....#", "......#", "......#", ".#####.", "#......", "#......", "#......", "#######"],
    "3": [".#####.", "#.....#", "......#", "......#", "..####.", "......#", "......#", "#.....#", ".#####."],
    "4": ["....##.", "...#.#.", "..#..#.", ".#...#.", "#....#.", "#######", ".....#.", ".....#.", ".....#."],
    "5": ["#######", "#......", "#......", "######.", "......#", "......#", "......#", "#.....#", ".#####."],
    "6": [".#####.", "#......", "#......", "######.", "#.....#", "#.....#", "#.....#", "#.....#", ".#####."],
    "7": ["#######", "#.....#", "......#", ".....#.", "....#..", "...#...", "...#...", "...#...", "...#..."],
    "8": [".#####.", "#.....#", "#.....#", "#.....#", ".#####.", "#.....#", "#.....#", "#.....#", ".#####."],
    "9": [".#####.", "#.....#", "#.....#", "#.....#", ".######", "......#", "......#", "......#", ".#####."],
    "/": ["......#", ".....#.", ".....#.", "....#..", "...#...", "..#....", ".#.....", ".#.....", "#......"],
}
FUENTE = FUENTE_FINA
FUENTE_ANCHO, FUENTE_ALTO, AVANCE = 7, 9, 9
# Barra de experiencia del arma en la mano, bajo el marco del HUD. El juego cuenta los usos de cada arma
# (weapon_level_records[arma].use_count, Player_CountWeaponUse) y sube su nivel a los 180 y a los 480 usos.
# La rutina va en Debug_RunStartMenu, que solo llama Debug_LoopUntilNewGame, que nada llama.
BARRA_HUECO_VA, BARRA_HUECO_FIN = 0x1AF298, 0x1AF670
BARRA_HUECO_FIRMA = bytes.fromhex("e0fcbd274400023cf002b7ff4400033c")
REGISTROS_ARMA = 0x3671E0                       # weapon_level_records (0x22 bytes cada uno)
BARRA_X, BARRA_Y, BARRA_ANCHO, BARRA_ALTO = 0x56, 0x5D, 100, 4    # píxeles del HUD (como Hud_InitSprite)
COLOR_BARRA = 0x8030B8F0                        # oro
COLOR_BARRA_VACIA = 0x80202630
COLOR_MARCO = 0x80000000     # píxeles (el alto en filas de 2 líneas)
COLOR_VIDA = 0x80A0D8E8                         # a b g r: hueso claro, como las barras de durabilidad
COLOR_SOMBRA = 0x80000000


def _rect_glifo(filas):
    """Rectángulos (x0, y0, x1, y1) que cubren el glifo: tramos por fila, unidos hacia abajo si se repiten."""
    abiertos, out = {}, []
    for y, fila in enumerate(filas + ["." * len(filas[0])]):
        tramos, x = set(), 0
        while x < len(fila):
            if fila[x] == "#":
                x0 = x
                while x < len(fila) and fila[x] == "#":
                    x += 1
                tramos.add((x0, x))
            else:
                x += 1
        for t in list(abiertos):
            if t not in tramos:
                out.append((t[0], abiertos.pop(t), t[1], y))
        for t in tramos:
            abiertos.setdefault(t, y)
    return out


def _hi_lo(v):
    lo = v & 0xFFFF
    hi = ((v >> 16) + (1 if lo & 0x8000 else 0)) & 0xFFFF
    return hi, lo


def _datos_fuente(base):
    """Tabla de 11 desplazamientos (u16) y, por glifo, nº de rectángulos + rectángulos (4 bytes)."""
    glifos = [_rect_glifo(FUENTE[c]) for c in "0123456789/"]
    cab = 2 * len(glifos)
    cuerpo, offs = b"", []
    for g in glifos:
        offs.append(cab + len(cuerpo))
        cuerpo += bytes([len(g)]) + b"".join(bytes(r) for r in g)
    return struct.pack(f"<{len(offs)}H", *offs) + cuerpo


def codigo_vida(cruz=False):
    datos = _datos_fuente(0)
    tabla = (VIDA_HUECO_FIN - len(datos)) & ~3      # datos al final del hueco
    th, tl = _hi_lo(tabla)
    oh, ol = _hi_lo(ORBE)
    ph, pl = _hi_lo(PLAYER_STATE)
    paso = AVANCE * 16

    def cifras(reg_valor, tope):
        """Mete en la cadena (al revés) las cifras de reg_valor; s1 = longitud."""
        return [("slt", "v0", reg_valor, "zero"), ("beq", "v0", "zero", f"p{tope}"), ("nop",),
                ("move", reg_valor, "zero"),
                f"p{tope}", ("slti", "v0", reg_valor, 10000), ("bne", "v0", "zero", f"d{tope}"), ("nop",),
                ("addiu", reg_valor, "zero", 9999),
                f"d{tope}", ("div", reg_valor, "t3"), ("nop",), ("nop",), ("mflo", reg_valor), ("mfhi", "t1"),
                ("nop",), ("nop",), ("addu", "t2", "sp", "s1"), ("sb", "t1", 0xB0, "t2"), ("addiu", "s1", "s1", 1),
                ("bne", reg_valor, "zero", f"d{tope}"), ("nop",)]
    prog = [("addiu", "sp", "sp", -0xD0), ("sd", "ra", 0xC0, "sp"), ("sd", "s0", 0x40, "sp"),
            ("sd", "s1", 0x50, "sp"), ("sd", "s2", 0x60, "sp"), ("sd", "s3", 0x70, "sp"),
            ("sd", "s4", 0x80, "sp"), ("sd", "s5", 0x90, "sp"), ("sd", "s6", 0xA0, "sp"),
            ("sd", "s7", 0xA8, "sp"),
            ("jal", SPRITE_TEXTURADO), ("nop",),              # lo que hacía Hud_Draw aquí
            # cadena al revés en sp+0xB0..: cifras de la máxima, '/', cifras de la vida
            ("move", "s1", "zero"), ("addiu", "t3", "zero", 10),
            ("lui", "t0", ph), ("addiu", "t0", "t0", pl), ("lw", "s0", 0x58, "t0")]
    prog += cifras("s0", "m")
    prog += [("addiu", "t1", "zero", 10), ("addu", "t2", "sp", "s1"), ("sb", "t1", 0xB0, "t2"),
             ("addiu", "s1", "s1", 1),
             ("lui", "t0", ph), ("addiu", "t0", "t0", pl), ("lw", "s0", 0xB4, "t0")]
    prog += cifras("s0", "v")
    prog += [  # centro del orbe; s7 = x del primer carácter, s3 = y de arriba (12.4)
        ("lui", "t0", oh), ("addiu", "t0", "t0", ol),
        ("lhu", "t1", 0x20, "t0"), ("lhu", "t2", 0x30, "t0"), ("addu", "t1", "t1", "t2"), ("srl", "t1", "t1", 1),
        ("lhu", "t4", 0x22, "t0"), ("lhu", "t2", 0x32, "t0"), ("addu", "t4", "t4", "t2"), ("srl", "t4", "t4", 1),
        ("addiu", "s3", "t4", -(FUENTE_ALTO * 16 // 2)),
        ("sll", "t2", "s1", 7), ("sll", "t5", "s1", 4), ("addu", "t2", "t2", "t5"),   # s1 * AVANCE(9) * 16
        ("addiu", "t2", "t2", -(AVANCE - FUENTE_ANCHO) * 16), ("srl", "t2", "t2", 1), ("subu", "s7", "t1", "t2"),
        ("move", "s6", "zero"),                                    # s6: 0 = pasada de sombra, 1 = de color
        "pasada", ("move", "s2", "s7"), ("move", "s4", "s1"),     # s4: caracteres que quedan
        "car", ("addiu", "s4", "s4", -1), ("addu", "t0", "sp", "s4"), ("lbu", "t5", 0xB0, "t0"),
        ("lui", "t6", th), ("addiu", "t6", "t6", tl), ("sll", "t5", "t5", 1), ("addu", "t5", "t5", "t6"),
        ("lhu", "t5", 0, "t5"), ("addu", "s0", "t6", "t5"),        # s0 -> glifo
        ("lbu", "s5", 0, "s0"), ("addiu", "s0", "s0", 1),          # s5 = rectángulos que quedan
        "rect", ("lbu", "t2", 0, "s0"), ("lbu", "t3", 1, "s0"), ("lbu", "t4", 2, "s0"), ("lbu", "t5", 3, "s0"),
        ("sll", "t2", "t2", 4), ("sll", "t4", "t4", 4), ("sll", "t3", "t3", 4), ("sll", "t5", "t5", 4),
        ("addu", "t2", "t2", "s2"), ("addu", "t4", "t4", "s2"), ("addu", "t3", "t3", "s3"), ("addu", "t5", "t5", "s3"),
        ("bne", "s6", "zero", "color"), ("lui", "t6", COLOR_VIDA >> 16),
        ("addiu", "t3", "t3", 16), ("addiu", "t5", "t5", 16),     # sombra: un píxel hacia abajo
        ("beq", "zero", "zero", "dibuja"), ("lui", "t6", COLOR_SOMBRA >> 16),
        "color", ("ori", "t6", "t6", COLOR_VIDA & 0xFFFF),
        "dibuja", ("sw", "zero", 0x10, "sp"), ("sw", "t6", 0x14, "sp"),
        ("sh", "t2", 0x20, "sp"), ("sh", "t3", 0x22, "sp"), ("sw", "zero", 0x24, "sp"),
        ("sh", "t4", 0x30, "sp"), ("sh", "t5", 0x32, "sp"), ("sw", "zero", 0x34, "sp"),
        ("jal", SPRITE_PLANO), ("move", "a0", "sp"),
        ("addiu", "s0", "s0", 4), ("addiu", "s5", "s5", -1), ("nop",), ("nop",),
        ("bne", "s5", "zero", "rect"), ("nop",),
        ("addiu", "s2", "s2", paso), ("nop",), ("nop",), ("nop",),
        ("bne", "s4", "zero", "car"), ("nop",),
        ("addiu", "s6", "s6", 1), ("slti", "t0", "s6", 2), ("nop",), ("nop",),
        ("bne", "t0", "zero", "pasada"), ("nop",),
    ] + ([("jal", CRUZ_HUECO_VA), ("nop",)] if cruz else []) + [                # cruz de equipo rápido
        ("ld", "s7", 0xA8, "sp"), ("ld", "ra", 0xC0, "sp"), ("ld", "s0", 0x40, "sp"), ("ld", "s1", 0x50, "sp"),
        ("ld", "s2", 0x60, "sp"), ("ld", "s3", 0x70, "sp"), ("ld", "s4", 0x80, "sp"), ("ld", "s5", 0x90, "sp"),
        ("ld", "s6", 0xA0, "sp"), ("jr", "ra"), ("addiu", "sp", "sp", 0xD0)]
    code = _ensamblar(prog, VIDA_HUECO_VA)
    assert VIDA_HUECO_VA + len(code) <= tabla, (len(code), len(datos))
    hueco = bytearray(VIDA_HUECO_FIN - VIDA_HUECO_VA)
    hueco[:len(code)] = code
    hueco[tabla - VIDA_HUECO_VA:tabla - VIDA_HUECO_VA + len(datos)] = datos
    return bytes(hueco)


# Vida con las cifras de la fuente del menú del juego (menu/font.tmr): se suben con el resto de texturas del bloque
# de la cruz (en 099.map) y se dibujan como sprites con textura, centradas en el orbe, con una sombra debajo.
VIDA_ESCALA_X, VIDA_ESCALA_Y = 13, 17          # 1/16 de píxel del HUD por téxel (el menú se ve con otra proporción)
VIDA_ALTO_TEX = 19
COLOR_VIDA_TEX = 0x8098A8B0                    # a b g r: gris cálido claro, como los números del menú
COLOR_VIDA_SOMBRA = 0x80000000


def codigo_vida_textura(cruz, off_bloque):
    import kf4_cruz as kc
    oh, ol = _hi_lo(off_bloque)
    mh, ml = _hi_lo(MAP_SLOT_MEMORY)
    orh, orl = _hi_lo(ORBE)
    ph, pl = _hi_lo(PLAYER_STATE)
    f0 = int.from_bytes(kc.FIRMA[0:4], "little")
    f1 = int.from_bytes(kc.FIRMA[4:8], "little")
    SX, SY, H = VIDA_ESCALA_X, VIDA_ESCALA_Y, VIDA_ALTO_TEX

    def por_sx(reg_out, reg_in):       # reg_out = reg_in * SX, con desplazamientos
        bits = [b for b in range(8) if SX >> b & 1]
        out = [("sll", reg_out, reg_in, bits[-1])]
        for b in bits[:-1]:
            out += [("sll", "t8", reg_in, b), ("addu", reg_out, reg_out, "t8")]
        return out

    def cifras(reg_valor, tope):
        return [("slt", "v0", reg_valor, "zero"), ("beq", "v0", "zero", f"p{tope}"), ("nop",),
                ("move", reg_valor, "zero"),
                f"p{tope}", ("slti", "v0", reg_valor, 10000), ("bne", "v0", "zero", f"d{tope}"), ("nop",),
                ("addiu", reg_valor, "zero", 9999),
                f"d{tope}", ("div", reg_valor, "t3"), ("nop",), ("nop",), ("mflo", reg_valor), ("mfhi", "t1"),
                ("nop",), ("nop",), ("addu", "t2", "sp", "s1"), ("sb", "t1", 0xB0, "t2"), ("addiu", "s1", "s1", 1),
                ("bne", reg_valor, "zero", f"d{tope}"), ("nop",)]
    p = [("addiu", "sp", "sp", -0x110), ("sd", "ra", 0x100, "sp"), ("sd", "s0", 0x60, "sp"), ("sd", "s1", 0x68, "sp"),
         ("sd", "s2", 0x70, "sp"), ("sd", "s3", 0x78, "sp"), ("sd", "s4", 0x80, "sp"), ("sd", "s5", 0x88, "sp"),
         ("sd", "s6", 0x90, "sp"), ("sd", "s7", 0x98, "sp"),
         ("jal", SPRITE_TEXTURADO), ("nop",),                       # lo que hacía Hud_Draw aquí
         ("lui", "t0", mh), ("addiu", "t0", "t0", ml)]
    for k, hueco in enumerate((0x1C, 0x1C + 0x58)):              # el bloque, en cualquiera de los dos mapas
        p += [("lw", "t1", hueco, "t0"), ("beq", "t1", "zero", f"no{k}"), ("nop",),
              ("lui", "t2", oh), ("addiu", "t2", "t2", ol), ("addu", "t1", "t1", "t2"),
              ("lw", "t3", 0, "t1"), ("lui", "t4", f0 >> 16), ("ori", "t4", "t4", f0 & 0xFFFF),
              ("bne", "t3", "t4", f"no{k}"), ("nop",),
              ("lw", "t3", 4, "t1"), ("lui", "t4", f1 >> 16), ("ori", "t4", "t4", f1 & 0xFFFF),
              ("bne", "t3", "t4", f"no{k}"), ("nop",),
              ("beq", "zero", "zero", "hay"), ("move", "s0", "t1"), f"no{k}"]
    p += [("beq", "zero", "zero", "sin_texto"), ("nop",),
          "hay", ("lbu", "a1", kc.OFF_CIFRAS_TROZO, "s0"), ("addiu", "t0", "zero", 0xFF),
          ("beq", "a1", "t0", "sin_texto"), ("nop",),
          ("jal", TABLA_SUBIR_UNA), ("addiu", "a0", "s0", kc.OFF_TABLA),
          ("addiu", "s6", "s0", kc.OFF_CIFRAS_TAB),
          # cadena al revés en sp+0xB0..: cifras de la máxima, "/" (10), cifras de la vida
          ("move", "s1", "zero"), ("addiu", "t3", "zero", 10),
          ("lui", "t0", ph), ("addiu", "t0", "t0", pl), ("lw", "s7", 0x58, "t0")]
    p += cifras("s7", "m")
    p += [("addiu", "t1", "zero", 10), ("addu", "t2", "sp", "s1"), ("sb", "t1", 0xB0, "t2"), ("addiu", "s1", "s1", 1),
          ("lui", "t0", ph), ("addiu", "t0", "t0", pl), ("lw", "s7", 0xB4, "t0"), ("addiu", "t3", "zero", 10)]
    p += cifras("s7", "v")
    # ancho total: suma de (ancho + 1) * SX, menos el último hueco
    p += [("move", "t4", "zero"), ("move", "t6", "s1"),
          "suma", ("addiu", "t6", "t6", -1), ("addu", "t0", "sp", "t6"), ("lbu", "t1", 0xB0, "t0"),
          ("sll", "t1", "t1", 1), ("addu", "t1", "t1", "s6"), ("lbu", "t2", 1, "t1"), ("addiu", "t2", "t2", 1)]
    p += por_sx("t7", "t2")
    p += [("addu", "t4", "t4", "t7"), ("bne", "t6", "zero", "suma"), ("nop",), ("addiu", "t4", "t4", -SX),
          # centro del orbe
          ("lui", "t0", orh), ("addiu", "t0", "t0", orl),
          ("lhu", "t1", 0x20, "t0"), ("lhu", "t2", 0x30, "t0"), ("addu", "t1", "t1", "t2"), ("srl", "t1", "t1", 1),
          ("lhu", "t5", 0x22, "t0"), ("lhu", "t2", 0x32, "t0"), ("addu", "t5", "t5", "t2"), ("srl", "t5", "t5", 1),
          ("srl", "t4", "t4", 1), ("subu", "s7", "t1", "t4"),                       # s7: x del primer carácter
          ("addiu", "s3", "t5", -(H * SY // 2)),                                    # s3: y de arriba
          ("move", "s5", "zero"),                                                   # 0 sombra, 1 color
          "pasada", ("move", "s2", "s7"), ("move", "s4", "s1"),
          "car", ("addiu", "s4", "s4", -1), ("addu", "t0", "sp", "s4"), ("lbu", "t1", 0xB0, "t0"),
          ("sll", "t1", "t1", 1), ("addu", "t1", "t1", "s6"), ("lbu", "t2", 0, "t1"), ("lbu", "t3", 1, "t1"),
          ("ld", "t4", kc.OFF_CIFRAS_TEX, "s0"), ("sd", "t4", 0x10, "sp"),
          ("ld", "t4", kc.OFF_CIFRAS_TEX + 8, "s0"), ("sd", "t4", 0x18, "sp"),
          ("addiu", "t4", "zero", 0x156), ("sw", "t4", 0x20, "sp"),
          ("lui", "t6", COLOR_VIDA_SOMBRA >> 16), ("bne", "s5", "zero", "color"), ("ori", "t6", "t6", COLOR_VIDA_SOMBRA & 0xFFFF),
          ("beq", "zero", "zero", "puesto"), ("addiu", "t7", "s3", 16),             # sombra: 1 píxel abajo
          "color", ("lui", "t6", COLOR_VIDA_TEX >> 16), ("ori", "t6", "t6", COLOR_VIDA_TEX & 0xFFFF),
          ("move", "t7", "s3"),
          "puesto", ("sw", "t6", 0x24, "sp"),
          ("sh", "s2", 0x30, "sp"), ("sh", "t7", 0x32, "sp"), ("sw", "zero", 0x34, "sp"),
          ("sll", "t8", "t2", 4), ("sw", "t8", 0x38, "sp"), ("sw", "zero", 0x3C, "sp")]
    p += por_sx("t9", "t3")
    p += [("addu", "t4", "s2", "t9"), ("sh", "t4", 0x40, "sp"),
          ("addiu", "t4", "t7", H * SY), ("sh", "t4", 0x42, "sp"), ("sw", "zero", 0x44, "sp"),
          ("addu", "t8", "t2", "t3"), ("sll", "t8", "t8", 4), ("sw", "t8", 0x48, "sp"),
          ("addiu", "t8", "zero", H * 16), ("sw", "t8", 0x4C, "sp"),
          ("addu", "s2", "s2", "t9"), ("addiu", "s2", "s2", SX),                    # siguiente carácter
          ("jal", SPRITE_TEXTURADO), ("addiu", "a0", "sp", 0x10),
          ("bne", "s4", "zero", "car"), ("nop",),
          ("addiu", "s5", "s5", 1), ("slti", "t0", "s5", 2), ("bne", "t0", "zero", "pasada"), ("nop",),
          "sin_texto"] + ([("jal", CRUZ_HUECO_VA), ("nop",)] if cruz else []) + [
          ("ld", "s7", 0x98, "sp"), ("ld", "s6", 0x90, "sp"), ("ld", "s5", 0x88, "sp"), ("ld", "s4", 0x80, "sp"),
          ("ld", "s3", 0x78, "sp"), ("ld", "s2", 0x70, "sp"), ("ld", "s1", 0x68, "sp"), ("ld", "s0", 0x60, "sp"),
          ("ld", "ra", 0x100, "sp"), ("jr", "ra"), ("addiu", "sp", "sp", 0x110)]
    code = _ensamblar(p, VIDA_HUECO_VA)
    assert len(code) <= VIDA_HUECO_FIN - VIDA_HUECO_VA, len(code)
    return code + bytes(VIDA_HUECO_FIN - VIDA_HUECO_VA - len(code))


def _hud_x(px):
    return (px + 0x10 + 0x6C0) << 4


def _hud_y(py):
    return (py + 0x10 + 0x720) << 4


def codigo_barra_arma():
    ph, pl = _hi_lo(PLAYER_STATE)
    rh, rl = _hi_lo(REGISTROS_ARMA)
    W = BARRA_ANCHO * 16
    x0, y0 = _hud_x(BARRA_X), _hud_y(BARRA_Y)
    x1, y1 = _hud_x(BARRA_X + BARRA_ANCHO), _hud_y(BARRA_Y + BARRA_ALTO)

    def rect(ax, ay, bx, by, color, ax_reg=None, bx_reg=None):
        """t2..t5 = esquinas, t6 = color; ax_reg/bx_reg: sumar un registro a la x."""
        ch, cl = _hi_lo(color)
        out = [("addiu", "t2", "zero", ax), ("addiu", "t3", "zero", ay), ("addiu", "t4", "zero", bx),
               ("addiu", "t5", "zero", by), ("lui", "t6", ch), ("addiu", "t6", "t6", cl)]
        if bx_reg:
            out.append(("addu", "t4", "t4", bx_reg))
        return out + [("jal", "rect"), ("nop",)]

    def division(num, den):   # s2 = num * W / den
        return [("addiu", "t1", "zero", W), ("mult", num, "t1"), ("nop",), ("nop",), ("mflo", "t2"),
                ("nop",), ("nop",), ("addiu", "t3", "zero", den), ("div", "t2", "t3"), ("nop",), ("nop",),
                ("mflo", "s2"), ("nop",), ("nop",)]
    prog = [("addiu", "sp", "sp", -0x80), ("sd", "ra", 0x70, "sp"), ("sd", "s0", 0x40, "sp"),
            ("sd", "s1", 0x50, "sp"), ("sd", "s2", 0x60, "sp"),
            ("lui", "t0", ph), ("addiu", "t0", "t0", pl), ("lbu", "t1", 0x3C, "t0"),      # arma en la mano
            ("sll", "t2", "t1", 5), ("sll", "t3", "t1", 1), ("addu", "t2", "t2", "t3"),   # * 0x22
            ("lui", "t4", rh), ("addiu", "t4", "t4", rl), ("addu", "s0", "t4", "t2"),
            ("lhu", "s1", 0x16, "s0"),                                                     # usos
            ("slti", "t0", "s1", 180), ("beq", "t0", "zero", "n2"), ("nop",)]
    prog += division("s1", 180) + [("addiu", "s1", "zero", 1), ("beq", "zero", "zero", "dibuja"), ("nop",),
                                   "n2", ("slti", "t0", "s1", 480), ("beq", "t0", "zero", "lleno"), ("nop",),
                                   ("addiu", "s1", "s1", -180)]
    prog += division("s1", 300) + [("addiu", "s1", "zero", 2), ("beq", "zero", "zero", "dibuja"), ("nop",),
                                   "lleno", ("addiu", "s2", "zero", W), ("addiu", "s1", "zero", 3),
                                   "dibuja"]
    prog += rect(x0 - 16, y0 - 32, x1 + 16, y1 + 32, COLOR_MARCO)
    prog += rect(x0, y0, x1, y1, COLOR_BARRA_VACIA)
    prog += [("beq", "s2", "zero", "pips"), ("nop",)]
    prog += rect(x0, y0, x0, y1, COLOR_BARRA, bx_reg="s2")
    prog += ["pips"]
    for i in range(3):      # nivel del arma: tres marcas a la derecha de la barra
        px = BARRA_X + BARRA_ANCHO + 5 + i * 7
        a, b = _hud_x(px), _hud_x(px + 4)
        prog += rect(a - 16, y0 - 32, b + 16, y1 + 32, COLOR_MARCO)
        prog += [("slti", "t0", "s1", i + 1), ("bne", "t0", "zero", f"np{i}"), ("nop",)]
        prog += rect(a, y0, b, y1, COLOR_BARRA)
        prog += [f"np{i}"]
    prog += [("ld", "ra", 0x70, "sp"), ("ld", "s0", 0x40, "sp"), ("ld", "s1", 0x50, "sp"), ("ld", "s2", 0x60, "sp"),
             ("jr", "ra"), ("addiu", "sp", "sp", 0x80),
             # subrutina: rectángulo plano con t2..t6
             "rect", ("sd", "ra", 0x78, "sp"), ("sw", "zero", 0x10, "sp"), ("sw", "t6", 0x14, "sp"),
             ("sh", "t2", 0x20, "sp"), ("sh", "t3", 0x22, "sp"), ("sw", "zero", 0x24, "sp"),
             ("sh", "t4", 0x30, "sp"), ("sh", "t5", 0x32, "sp"), ("sw", "zero", 0x34, "sp"),
             ("jal", SPRITE_PLANO), ("move", "a0", "sp"),
             ("ld", "ra", 0x78, "sp"), ("jr", "ra"), ("nop",)]
    code = _ensamblar(prog, BARRA_HUECO_VA)
    hueco = BARRA_HUECO_FIN - BARRA_HUECO_VA
    assert BARRA_HUECO_VA + len(code) <= BARRA_HUECO_FIN, len(code)
    return code + bytes(hueco - len(code))


# ======================= Cruz de equipo rápido (estilo Dark Souls) =======================
# Con el mando de dos sticks la cruceta queda libre. Se lee aparte (Input_ReadPort la quita de los botones
# de andar y la guarda en CRUZ_PULSADO) y, en cada fotograma con HUD:
#   derecha = siguiente arma que tienes, izquierda = siguiente escudo (ninguno con armas a dos manos),
#   arriba = siguiente consumible (hierbas, frutos...: queda en el atajo, se usa con SELECT).
#   abajo = magia: aún no (cambiarla exige cargar su banco de sonido en un punto seguro del bucle).
# Al cambiar de arma se pide recargar su modelo como hace el juego al usar objetos (GameStatus.bit14) y
# se recalculan las estadísticas (Player_RecomputeStats). Se dibujan cuatro casillas abajo a la izquierda.
# El código va en Debug_PickMap y Debug_EditIniNumber (los llamaba solo el menú de depuración, que nada llama).
CRUZ_HUECO_VA, CRUZ_HUECO_FIN = 0x1AF670, 0x1AFB60
CRUZ_HUECO_FIRMA = bytes.fromhex("40ffbd2700c00234")
CRUZ_DATOS = CRUZ_HUECO_FIN - 0x10          # +0 u16 pulsado, +2 u8 escudo recordado, +3 u8 casilla, +4 u16 destello
CRUZ_PULSADO = CRUZ_DATOS
ITEM_COUNTS = 0x369070
WEAPON_DEFS = 0x41B178
GAME_STATUS = 0x38C490
RECALCULAR = 0x1B8B30                        # Player_RecomputeStats
# el dibujo de la cruz (marcos e ilustraciones del juego) va en el hueco de Debug_RunStartMenu; las texturas, en
# un bloque dentro de 099.map (kf4_cruz.py) que se encuentra por su firma en el mapa cargado
DIBUJO_CRUZ_VA = BARRA_HUECO_VA
MAP_SLOT_MEMORY = 0x438330                   # map_slot_memory[2] (0x58 cada uno); +0x1C: el archivo de mapa cargado
TABLA_SUBIR_UNA = 0x10A348                   # TextureTable_QueueOne(tabla, índice)
DORADO = 0x8060A8C0                          # color del marco recién cambiado (r, g, b, a)


def codigo_dibujo_cruz(off_bloque, con_texto=True):
    import kf4_cruz as kc
    oh, ol = _hi_lo(off_bloque)
    mh, ml = _hi_lo(MAP_SLOT_MEMORY)
    ph, pl = _hi_lo(PLAYER_STATE)
    dh, dl = _hi_lo(CRUZ_DATOS)
    ih, il = _hi_lo(ITEM_COUNTS)
    wd = _hi_lo(WEAPON_DEFS + 0x63)
    f0 = int.from_bytes(kc.FIRMA[0:4], "little")
    f1 = int.from_bytes(kc.FIRMA[4:8], "little")
    p = [("addiu", "sp", "sp", -0x80), ("sd", "ra", 0x70, "sp"), ("sd", "s0", 0x40, "sp"), ("sd", "s1", 0x50, "sp"),
         ("sd", "s2", 0x60, "sp"), ("sd", "s3", 0x48, "sp"), ("sd", "s4", 0x58, "sp"),
         ("lui", "t0", mh), ("addiu", "t0", "t0", ml)]
    for k, hueco in enumerate((0x1C, 0x1C + 0x58)):          # el mapa puede estar en cualquiera de los dos huecos
        p += [("lw", "t1", hueco, "t0"), ("beq", "t1", "zero", f"no{k}"), ("nop",),
              ("lui", "t2", oh), ("addiu", "t2", "t2", ol), ("addu", "t1", "t1", "t2"),
              ("lw", "t3", 0, "t1"), ("lui", "t4", f0 >> 16), ("ori", "t4", "t4", f0 & 0xFFFF),
              ("bne", "t3", "t4", f"no{k}"), ("nop",),
              ("lw", "t3", 4, "t1"), ("lui", "t4", f1 >> 16), ("ori", "t4", "t4", f1 & 0xFFFF),
              ("bne", "t3", "t4", f"no{k}"), ("nop",),
              ("move", "s0", "t1"), ("beq", "zero", "zero", "hay"), ("nop",), f"no{k}"]
    p += [("beq", "zero", "zero", "salir"), ("nop",),
          "hay", ("lui", "s1", ph), ("addiu", "s1", "s1", pl), ("lui", "s2", dh), ("addiu", "s2", "s2", dl),
          ("addiu", "s3", "s0", kc.OFF_TABLA),
          ("move", "a0", "s3"), ("jal", TABLA_SUBIR_UNA), ("move", "a1", "zero"),       # el marco
          ("lhu", "t8", 4, "s2"), ("beq", "t8", "zero", "sin_destello"), ("nop",),
          ("addiu", "t8", "t8", -1), ("sh", "t8", 4, "s2"), ("beq", "zero", "zero", "con_destello"), ("lbu", "s4", 3, "s2"),
          "sin_destello", ("addiu", "s4", "zero", 9),
          "con_destello"]
    for c in range(4):                                        # los cuatro marcos
        p += [("addiu", "a0", "s0", kc.OFF_SPRITES + c * 0x40),
              ("lui", "t9", 0x8080), ("ori", "t9", "t9", 0x8080),
              ("addiu", "t8", "zero", c), ("bne", "s4", "t8", f"m{c}"), ("nop",),
              ("lui", "t9", DORADO >> 16), ("ori", "t9", "t9", DORADO & 0xFFFF),
              f"m{c}", ("sw", "t9", 0x14, "a0"), ("jal", SPRITE_TEXTURADO), ("nop",)]

    def icono(off_mapa, reg_idx, casilla, salto):
        return [("addu", "t1", "s0", reg_idx), ("lbu", "a1", off_mapa, "t1"), ("addiu", "t2", "zero", 0xFF),
                ("beq", "a1", "t2", salto), ("nop",),
                ("jal", TABLA_SUBIR_UNA), ("move", "a0", "s3"),
                ("jal", SPRITE_TEXTURADO), ("addiu", "a0", "s0", kc.OFF_SPRITES + (4 + casilla) * 0x40)]
    p += [("lbu", "t0", 0x3C, "s1"), ("beq", "t0", "zero", "escudo"), ("nop",)] + icono(kc.OFF_ARMAS, "t0", 0, "escudo")
    p += ["escudo", ("lbu", "t0", 0x3C, "s1"),
          ("sll", "t8", "t0", 4), ("sll", "t9", "t0", 7), ("addu", "t8", "t8", "t9"),
          ("lui", "t9", wd[0]), ("addiu", "t9", "t9", wd[1]), ("addu", "t8", "t8", "t9"), ("lbu", "t8", 0, "t8"),
          ("bne", "t8", "zero", "objeto"), ("nop",),                   # con un arma a dos manos no hay escudo
          ("lbu", "t0", 0x3E, "s1"), ("beq", "t0", "zero", "objeto"), ("nop",)] + icono(kc.OFF_ESCUDOS, "t0", 1, "objeto")
    p += ["objeto", ("lbu", "t0", 0x48, "s1"), ("addiu", "t1", "zero", 1), ("bne", "t0", "t1", "magia"), ("nop",),
          ("lhu", "t0", 0x46, "s1"), ("sltiu", "t1", "t0", 32), ("beq", "t1", "zero", "magia"), ("nop",),
          ("lui", "t1", ih), ("addiu", "t1", "t1", il), ("addu", "t1", "t1", "t0"), ("lbu", "t1", 0, "t1"),
          ("beq", "t1", "zero", "magia"), ("nop",)] + icono(kc.OFF_OBJETOS, "t0", 3, "magia")
    p += ["magia", ("lbu", "t0", 0x3D, "s1"), ("beq", "t0", "zero", "fin"), ("nop",),
          ("sltiu", "t1", "t0", 91), ("beq", "t1", "zero", "fin"), ("nop",)] + icono(kc.OFF_MAGIAS, "t0", 2, "fin")
    p += ["fin", ("jal", BARRAS_VA), ("nop",),                     # durabilidad del arma y del escudo
          ] + ([("jal", TEXTO_VA), ("move", "a0", "s0")] if con_texto else []) + [   # magia y cantidad del objeto
          # destello azul de la fuente que cura (CURA_DESTELLO lo pone la cura): toda la pantalla, se apaga
          ("lui", "t0", _hi_lo(CURA_DESTELLO)[0]), ("lhu", "t1", _hi_lo(CURA_DESTELLO)[1], "t0"),
          ("beq", "t1", "zero", "salir"), ("nop",),
          ("addiu", "t1", "t1", -1), ("sh", "t1", _hi_lo(CURA_DESTELLO)[1], "t0"),
          ("sll", "t2", "t1", 24), ("lui", "t3", COLOR_DESTELLO >> 16), ("ori", "t3", "t3", COLOR_DESTELLO & 0xFFFF),
          ("or", "t3", "t3", "t2"),
          ("sw", "zero", 0x10, "sp"), ("sw", "t3", 0x14, "sp"),
          ("ori", "t4", "zero", kc._hud(0)), ("sh", "t4", 0x20, "sp"), ("sh", "t4", 0x22, "sp"), ("sw", "zero", 0x24, "sp"),
          ("ori", "t4", "zero", kc._hud(512)), ("sh", "t4", 0x30, "sp"), ("sh", "t4", 0x32, "sp"), ("sw", "zero", 0x34, "sp"),
          ("jal", SPRITE_PLANO), ("move", "a0", "sp"),
          "salir", ("ld", "s4", 0x58, "sp"), ("ld", "s3", 0x48, "sp"), ("ld", "s2", 0x60, "sp"), ("ld", "s1", 0x50, "sp"),
          ("ld", "s0", 0x40, "sp"), ("ld", "ra", 0x70, "sp"), ("jr", "ra"), ("addiu", "sp", "sp", 0x80)]
    code = _ensamblar(p, DIBUJO_CRUZ_VA)
    assert len(code) <= BARRA_HUECO_FIN - DIBUJO_CRUZ_VA, len(code)
    return code + bytes(BARRA_HUECO_FIN - DIBUJO_CRUZ_VA - len(code))


# Barras de durabilidad bajo la casilla del arma y la del escudo: LevelRecord.level (la "Dura" del menú), que el
# desgaste baja de 100 hasta 50 (Attack_WearWeapon no la deja por debajo): llena a 100, vacía a 50.
BARRAS_VA = CRUZ_HUECO_VA + 0x300              # detrás de la lógica de la cruz, en su mismo hueco
REGISTROS_LLEVADO = 0x367B30                   # worn_item_level_records (escudo n: registro n)
DURA_ANCHO, DURA_ALTO = 32, 3                  # píxeles del HUD
COLOR_DURA = 0x80A0D8E8                        # a b g r: hueso claro
COLOR_DURA_FONDO = 0x70080808


def codigo_barras():
    import kf4_cruz as kc
    ph, pl = _hi_lo(PLAYER_STATE)
    wd = _hi_lo(WEAPON_DEFS + 0x63)
    W, H = DURA_ANCHO * 16, DURA_ALTO * 16

    def sitio(c):
        x, y = kc.CASILLAS[c]
        return kc._hud(x + (kc.CASILLA_W - DURA_ANCHO) // 2), kc._hud(y + kc.CASILLA_H + 3)

    def registro(base, reg_idx):          # t1 = base + reg_idx * 0x22
        h_, l_ = _hi_lo(base)
        return [("sll", "t1", reg_idx, 5), ("sll", "t2", reg_idx, 1), ("addu", "t1", "t1", "t2"),
                ("lui", "t2", h_), ("addiu", "t2", "t2", l_), ("addu", "t1", "t1", "t2")]

    def rect():                            # t2..t5 esquinas, t6 color
        return [("sw", "zero", 0x10, "sp"), ("sw", "t6", 0x14, "sp"), ("sh", "t2", 0x20, "sp"), ("sh", "t3", 0x22, "sp"),
                ("sw", "zero", 0x24, "sp"), ("sh", "t4", 0x30, "sp"), ("sh", "t5", 0x32, "sp"), ("sw", "zero", 0x34, "sp"),
                ("jal", SPRITE_PLANO), ("move", "a0", "sp")]
    (xa, ya), (xe, ye) = sitio(0), sitio(1)
    p = [("addiu", "sp", "sp", -0x80), ("sd", "ra", 0x70, "sp"), ("sd", "s0", 0x40, "sp"),
         ("lui", "s0", ph), ("addiu", "s0", "s0", pl),
         ("lbu", "t0", 0x3C, "s0"), ("beq", "t0", "zero", "escudo"), ("nop",)] + registro(REGISTROS_ARMA, "t0") + [
         ("lbu", "a1", 0x12, "t1"), ("ori", "a2", "zero", xa), ("jal", "barra"), ("ori", "a3", "zero", ya),
         "escudo", ("lbu", "t0", 0x3C, "s0"),
         ("sll", "t8", "t0", 4), ("sll", "t9", "t0", 7), ("addu", "t8", "t8", "t9"),
         ("lui", "t9", wd[0]), ("addiu", "t9", "t9", wd[1]), ("addu", "t8", "t8", "t9"), ("lbu", "t8", 0, "t8"),
         ("bne", "t8", "zero", "fin"), ("nop",),
         ("lbu", "t0", 0x3E, "s0"), ("beq", "t0", "zero", "fin"), ("nop",)] + registro(REGISTROS_LLEVADO, "t0") + [
         ("lbu", "a1", 0x12, "t1"), ("ori", "a2", "zero", xe), ("jal", "barra"), ("ori", "a3", "zero", ye),
         "fin", ("ld", "s0", 0x40, "sp"), ("ld", "ra", 0x70, "sp"), ("jr", "ra"), ("addiu", "sp", "sp", 0x80),
         # barra(a1 = durabilidad, a2 = x, a3 = y)
         "barra", ("sd", "ra", 0x78, "sp"), ("sw", "a1", 0x38, "sp"), ("sw", "a2", 0x3C, "sp"), ("sw", "a3", 0x68, "sp"),
         ("addiu", "t2", "a2", -16), ("addiu", "t3", "a3", -16), ("addiu", "t4", "a2", W + 16), ("addiu", "t5", "a3", H + 16),
         ("lui", "t6", COLOR_DURA_FONDO >> 16), ("ori", "t6", "t6", COLOR_DURA_FONDO & 0xFFFF)] + rect() + [
         ("lw", "t0", 0x38, "sp"), ("addiu", "t0", "t0", -50),            # 50..100 -> 0..50
         ("slt", "t1", "t0", "zero"), ("beq", "t1", "zero", "positivo"), ("nop",), ("move", "t0", "zero"),
         "positivo", ("slti", "t1", "t0", 51), ("bne", "t1", "zero", "tope"), ("nop",), ("addiu", "t0", "zero", 50),
         "tope", ("sll", "t1", "t0", 5), ("sll", "t2", "t0", 3), ("addu", "t1", "t1", "t2"), ("addu", "t1", "t1", "t0"),
         ("sra", "t0", "t1", 2),                                           # * 41 / 4 = * 512 / 50
         ("beq", "t0", "zero", "vacia"), ("nop",),
         ("lw", "t2", 0x3C, "sp"), ("lw", "t3", 0x68, "sp"), ("addu", "t4", "t2", "t0"), ("addiu", "t5", "t3", H),
         ("lui", "t6", COLOR_DURA >> 16), ("ori", "t6", "t6", COLOR_DURA & 0xFFFF)] + rect() + [
         "vacia", ("ld", "ra", 0x78, "sp"), ("jr", "ra"), ("nop",)]
    code = _ensamblar(p, BARRAS_VA)
    assert BARRAS_VA + len(code) <= CRUZ_DATOS, len(code)
    return code


def codigo_cruz(con_magia=True):
    ph, pl = _hi_lo(PLAYER_STATE)
    dh, dl = _hi_lo(CRUZ_DATOS)
    ic = lambda off: _hi_lo(ITEM_COUNTS + off)
    wd = _hi_lo(WEAPON_DEFS + 0x63)
    gs = _hi_lo(GAME_STATUS + 0x24)

    def mano_de(reg_w, reg_out):      # reg_out = weapon_defs[reg_w].action_handler_index
        return [("sll", "t8", reg_w, 4), ("sll", "t9", reg_w, 7), ("addu", "t8", "t8", "t9"),
                ("lui", "t9", wd[0]), ("addiu", "t9", "t9", wd[1]), ("addu", "t8", "t8", "t9"),
                ("lbu", reg_out, 0, "t8")]

    def tengo(base_item, reg_idx, reg_out):   # reg_out = item_counts[base_item + reg_idx]
        h_, l_ = ic(base_item)
        return [("lui", "t9", h_), ("addiu", "t9", "t9", l_), ("addu", "t9", "t9", reg_idx), ("lbu", reg_out, 0, "t9")]

    def destello(casilla):
        return [("addiu", "t8", "zero", casilla), ("sb", "t8", 3, "s1"), ("addiu", "t8", "zero", 45), ("sh", "t8", 4, "s1")]
    p = [("addiu", "sp", "sp", -0x80), ("sd", "ra", 0x70, "sp"), ("sd", "s0", 0x40, "sp"), ("sd", "s1", 0x50, "sp"),
         ("sd", "s2", 0x60, "sp"), ("sd", "s3", 0x48, "sp"),
         ("lui", "s0", ph), ("addiu", "s0", "s0", pl), ("lui", "s1", dh), ("addiu", "s1", "s1", dl),
         ("lhu", "s2", 0, "s1"), ("sh", "zero", 0, "s1"),
         # ---- derecha: arma ----
         ("andi", "t0", "s2", 0x20), ("beq", "t0", "zero", "izq"), ("nop",),
         ("lbu", "t5", 0x3C, "s0"), ("move", "t7", "t5"), ("addiu", "t6", "zero", 69),
         "a_bucle", ("addiu", "t7", "t7", 1), ("slti", "t8", "t7", 70), ("bne", "t8", "zero", "a_ok"), ("nop",),
         ("addiu", "t7", "zero", 1),
         "a_ok"] + tengo(150, "t7", "t9") + [
         ("bne", "t9", "zero", "a_hay"), ("nop",), ("addiu", "t6", "t6", -1), ("bne", "t6", "zero", "a_bucle"), ("nop",),
         ("beq", "zero", "zero", "izq"), ("nop",),
         "a_hay", ("beq", "t7", "t5", "izq"), ("nop",),
         ("sb", "t7", 0x3C, "s0"), ("sw", "zero", 0xBC, "s0")] + mano_de("t7", "t8") + [
         ("lbu", "t9", 0x3E, "s0"), ("beq", "t8", "zero", "a_una"), ("nop",),
         ("beq", "t9", "zero", "a_carga"), ("nop",), ("sb", "t9", 2, "s1"), ("sb", "zero", 0x3E, "s0"),
         ("beq", "zero", "zero", "a_carga"), ("nop",),
         "a_una", ("bne", "t9", "zero", "a_carga"), ("nop",), ("lbu", "t5", 2, "s1"), ("beq", "t5", "zero", "a_carga"),
         ("nop",)] + tengo(220, "t5", "t9") + [("beq", "t9", "zero", "a_carga"), ("nop",), ("sb", "t5", 0x3E, "s0"),
         "a_carga", ("lui", "t9", gs[0]), ("lw", "t8", gs[1], "t9"), ("ori", "t8", "t8", 0x4000), ("sw", "t8", gs[1], "t9"),
         ("jal", RECALCULAR), ("nop",)] + destello(0) + [
         # ---- izquierda: escudo ----
         "izq", ("andi", "t0", "s2", 0x80), ("beq", "t0", "zero", "arr"), ("nop",),
         ("lbu", "t5", 0x3C, "s0")] + mano_de("t5", "t8") + [("bne", "t8", "zero", "arr"), ("nop",),
         ("lbu", "t5", 0x3E, "s0"), ("move", "t7", "t5"), ("addiu", "t6", "zero", 26),
         "e_bucle", ("addiu", "t7", "t7", 1), ("slti", "t8", "t7", 26), ("bne", "t8", "zero", "e_ok"), ("nop",),
         ("move", "t7", "zero"),
         "e_ok", ("beq", "t7", "zero", "e_hay"), ("nop",)] + tengo(220, "t7", "t9") + [
         ("bne", "t9", "zero", "e_hay"), ("nop",), ("addiu", "t6", "t6", -1), ("bne", "t6", "zero", "e_bucle"), ("nop",),
         ("beq", "zero", "zero", "arr"), ("nop",),
         "e_hay", ("beq", "t7", "t5", "arr"), ("nop",), ("sb", "t7", 0x3E, "s0"), ("sb", "t7", 2, "s1"),
         ("lui", "t9", gs[0]), ("lw", "t8", gs[1], "t9"), ("ori", "t8", "t8", 0x4000), ("sw", "t8", gs[1], "t9"),
         ("jal", RECALCULAR), ("nop",)] + destello(1) + [
         # ---- abajo: consumible (1..30) en el atajo ----
         "arr", ("andi", "t0", "s2", 0x40), ("beq", "t0", "zero", "dibujo"), ("nop",),
         ("move", "t5", "zero"), ("lbu", "t8", 0x48, "s0"), ("addiu", "t9", "zero", 1), ("bne", "t8", "t9", "c_ini"),
         ("nop",), ("lhu", "t5", 0x46, "s0"),
         "c_ini", ("move", "t7", "t5"), ("addiu", "t6", "zero", 30),
         "c_bucle", ("addiu", "t7", "t7", 1), ("slti", "t8", "t7", 31), ("bne", "t8", "zero", "c_ok"), ("nop",),
         ("addiu", "t7", "zero", 1),
         "c_ok"] + tengo(0, "t7", "t9") + [
         ("bne", "t9", "zero", "c_hay"), ("nop",), ("addiu", "t6", "t6", -1), ("bne", "t6", "zero", "c_bucle"), ("nop",),
         ("beq", "zero", "zero", "dibujo"), ("nop",),
         "c_hay", ("beq", "t7", "t5", "dibujo"), ("nop",), ("addiu", "t8", "zero", 1), ("sb", "t8", 0x48, "s0"),
         ("sh", "t7", 0x46, "s0")] + destello(3) + [
         # ---- arriba: magia (MAGIA_VA) y dibujo: marcos e ilustraciones ----
         "dibujo"] + ([("jal", MAGIA_VA), ("move", "a0", "s2")] if con_magia else []) + [
         ("jal", DIBUJO_CRUZ_VA), ("nop",),
         "fin", ("ld", "s3", 0x48, "sp"), ("ld", "s2", 0x60, "sp"), ("ld", "s1", 0x50, "sp"), ("ld", "s0", 0x40, "sp"),
         ("ld", "ra", 0x70, "sp"), ("jr", "ra"), ("addiu", "sp", "sp", 0x80),
         ]
    code = _ensamblar(p, CRUZ_HUECO_VA)
    assert CRUZ_HUECO_VA + len(code) <= BARRAS_VA, len(code)
    code += bytes(BARRAS_VA - CRUZ_HUECO_VA - len(code)) + codigo_barras()
    return code + bytes(CRUZ_HUECO_FIN - CRUZ_HUECO_VA - len(code))


# ======================= Magia en la cruz (arriba) y textos de la cruz =======================
# Arriba = siguiente magia aprendida que se equipa (fx_table item_menu_magic 0, como la lista del menú: id
# 15 x escuela + 3 x hechizo + nivel, con spell_levels[escuela][hechizo] == nivel). Cambiarla exige cargar su
# banco de sonido (mgNNN): se hace donde el juego recarga los brazos tras usar un objeto (GameLoop_OpenRequestedMenu,
# GameStatus.bit14, cuando no hay cargas de mapa ni de sonido): se le pone el bit 14 y un aviso en CRUZ_DATOS+6, y
# el gancho carga los brazos, el banco (Sound_LoadMgBank) y pone la magia a cargar (charging_magic, gauge a 0).
# Va en ScreenDump_Clut / ScreenDump_Vram (0x200 bytes) y el dibujo de los textos en ScreenDump_Bmp / _Raw / _Data
# (0x480 bytes): volcados a host0 de depuración que nada llama.
MAGIA_VA, MAGIA_FIN = 0x19A3D8, 0x19A5D8
MAGIA_FIRMA = bytes.fromhex("01000c3cc0008c35")
TEXTO_VA, TEXTO_FIN = 0x19A6A0, 0x19AB20
TEXTO_FIRMA = bytes.fromhex("c0fdbd2788a4828f")
GANCHO_BRAZOS_VA = 0x1018A8                   # jal Player_LoadArmModels del bit 14
CARGAR_BRAZOS = 0x1BE0B8                      # Player_LoadArmModels
CARGAR_BANCO_MAGIA = 0x19FA80                 # Sound_LoadMgBank(número)
FX_TABLE = 0x402568                           # fx_table (param/magic.prm, 0x110 por magia)
SPELL_LEVELS = 0x3671C0                       # spell_levels[6][5]
MAGIA_AVISO = CRUZ_DATOS + 6
PAD_PULSADO = 0x41357A                        # pad_state.pressed del mando 1 (pad_state + 2)
BOTON_FUENTE = 0x4000                         # X (PAD_CROSS), el botón de mirar/coger del juego
CURA_VA = None                                # dentro del hueco de la magia (codigo_magia lo calcula)
CURA_DESTELLO = CRUZ_DATOS + 8                # u16: fotogramas que quedan del destello azul al curarse
CURA_DESTELLO_FOTOGRAMAS = 48
COLOR_DESTELLO = 0x00E8A060                   # b g r (el alfa va bajando con los fotogramas)
# textos: tamaño de cada letra en 1/16 de píxel del HUD (la celda es de 10 x 20 téxeles)
LETRA_W, LETRA_GW = 7 * 16, 9 * 16           # avance de la letra pequeña y de la cifra grande: un téxel del
                                              # atlas (kf4_cruz.LETRA_W, CIFRA_W) por píxel del HUD
COLOR_NOMBRE = 0x8098A8B0                     # a b g r
COLOR_MANA = 0x80E0A070
COLOR_CANTIDAD = 0x80A0B8C0
COLOR_SOMBRA = 0x80000000


def codigo_magia():
    import kf4_cruz as kc
    ph, pl = _hi_lo(PLAYER_STATE)
    ah, al = _hi_lo(MAGIA_AVISO)
    dh, dl = _hi_lo(CRUZ_DATOS)
    fh, fl = _hi_lo(FX_TABLE)
    sh_, sl_ = _hi_lo(SPELL_LEVELS)
    gs = _hi_lo(GAME_STATUS + 0x24)
    p = [("andi", "t0", "a0", 0x10), ("beq", "t0", "zero", "nada"), ("nop",),
         ("lui", "t9", ph), ("addiu", "t9", "t9", pl), ("lbu", "t5", 0x3D, "t9"),
         ("move", "t7", "t5"), ("addiu", "t6", "zero", 90),
         "bucle", ("addiu", "t7", "t7", 1), ("slti", "t8", "t7", 91), ("bne", "t8", "zero", "ok"), ("nop",),
         ("addiu", "t7", "zero", 1),
         "ok", ("addiu", "t0", "t7", -1), ("addiu", "t1", "zero", 3), ("div", "t0", "t1"), ("nop",), ("nop",),
         ("mflo", "t2"), ("mfhi", "t3"), ("nop",), ("nop",),
         ("lui", "t4", sh_), ("addiu", "t4", "t4", sl_), ("addu", "t4", "t4", "t2"), ("lbu", "t4", 0, "t4"),
         ("addiu", "t3", "t3", 1), ("bne", "t4", "t3", "otra"), ("nop",),
         ("sll", "t0", "t7", 8), ("sll", "t1", "t7", 4), ("addu", "t0", "t0", "t1"),
         ("lui", "t1", fh), ("addiu", "t1", "t1", fl), ("addu", "t0", "t0", "t1"), ("lbu", "t0", 0x102, "t0"),
         ("beq", "t0", "zero", "hay"), ("nop",),
         "otra", ("addiu", "t6", "t6", -1), ("bne", "t6", "zero", "bucle"), ("nop",),
         ("beq", "zero", "zero", "nada"), ("nop",),
         "hay", ("beq", "t7", "t5", "nada"), ("nop",),
         ("sb", "t7", 0x3D, "t9"),
         ("lui", "t0", ah), ("addiu", "t1", "zero", 1), ("sb", "t1", al, "t0"),
         ("lui", "t0", gs[0]), ("lw", "t1", gs[1], "t0"), ("ori", "t1", "t1", 0x4000), ("sw", "t1", gs[1], "t0"),
         ("lui", "t0", dh), ("addiu", "t0", "t0", dl), ("addiu", "t1", "zero", 2), ("sb", "t1", 3, "t0"),
         ("addiu", "t1", "zero", 45), ("sh", "t1", 4, "t0"),
         "nada", ("jr", "ra"), ("nop",),
         # gancho del bit 14: brazos y, si se cambió la magia, su banco de sonido
         "gancho", ("addiu", "sp", "sp", -0x20), ("sd", "ra", 0x10, "sp"),
         ("jal", CARGAR_BRAZOS), ("nop",),
         ("lui", "t0", ah), ("lbu", "t1", al, "t0"), ("beq", "t1", "zero", "g_fin"), ("nop",),
         ("sb", "zero", al, "t0"),
         ("lui", "t2", ph), ("addiu", "t2", "t2", pl), ("jal", CARGAR_BANCO_MAGIA), ("lbu", "a0", 0x3D, "t2"),
         ("lui", "t2", ph), ("addiu", "t2", "t2", pl), ("lbu", "t3", 0x3D, "t2"),
         ("sb", "t3", 0x264, "t2"), ("sw", "zero", 0xC0, "t2"),
         "g_fin", ("ld", "ra", 0x10, "sp"), ("jr", "ra"), ("addiu", "sp", "sp", 0x20),
         # cura(a0 = bloque de la cruz): al pulsar X cerca de una fuente (tabla OFF_FUENTES del bloque: n, alto², y
         # por fuente x, y, z, radio² en el espacio del juego) la vida se llena
         "cura", ("lui", "t4", PAD_PULSADO >> 16), ("lhu", "t4", PAD_PULSADO & 0xFFFF, "t4"),
         ("andi", "t4", "t4", BOTON_FUENTE), ("beq", "t4", "zero", "c_nada"), ("nop",),
         ("lw", "t0", kc.OFF_FUENTES, "a0"), ("beq", "t0", "zero", "c_nada"), ("nop",),
         ("addiu", "t1", "a0", kc.OFF_FUENTES + 16),
         ("lui", "t2", ph), ("addiu", "t2", "t2", pl),
         ("lwc1", "f0", 0, "t2"), ("lwc1", "f1", 4, "t2"), ("lwc1", "f2", 8, "t2"),
         "c_otra", ("lwc1", "f3", 0, "t1"), ("sub.s", "f3", "f3", "f0"), ("mul.s", "f3", "f3", "f3"),
         ("lwc1", "f4", 8, "t1"), ("sub.s", "f4", "f4", "f2"), ("mul.s", "f4", "f4", "f4"), ("add.s", "f3", "f3", "f4"),
         ("lwc1", "f5", 12, "t1"), ("c.lt.s", "f3", "f5"), ("nop",), ("bc1f", "c_sig"), ("nop",),
         ("lwc1", "f4", 4, "t1"), ("sub.s", "f4", "f4", "f1"), ("mul.s", "f4", "f4", "f4"),
         ("lwc1", "f5", kc.OFF_FUENTES + 4, "a0"), ("c.lt.s", "f4", "f5"), ("nop",), ("bc1f", "c_sig"), ("nop",),
         ("lw", "t3", 0x58, "t2"), ("sw", "t3", 0xB4, "t2"),                    # solo la vida, como las del 4
         ("lui", "t4", _hi_lo(CURA_DESTELLO)[0]), ("addiu", "t5", "zero", CURA_DESTELLO_FOTOGRAMAS),
         ("jr", "ra"), ("sh", "t5", _hi_lo(CURA_DESTELLO)[1], "t4"),             # destello azul (dibujo de la cruz)
         "c_sig", ("addiu", "t1", "t1", 16), ("addiu", "t0", "t0", -1), ("bne", "t0", "zero", "c_otra"), ("nop",),
         "c_nada", ("jr", "ra"), ("nop",)]
    code = _ensamblar(p, MAGIA_VA)
    assert len(code) <= MAGIA_FIN - MAGIA_VA, len(code)
    n_antes = sum(1 for x in p[:p.index("gancho")] if not isinstance(x, str))
    n_cura = sum(1 for x in p[:p.index("cura")] if not isinstance(x, str))
    global CURA_VA
    CURA_VA = MAGIA_VA + 4 * n_cura
    return code + bytes(MAGIA_FIN - MAGIA_VA - len(code)), MAGIA_VA + 4 * n_antes


def codigo_texto():
    """TEXTO_VA(a0 = bloque de la cruz): nombre de la magia encima de la casilla de arriba y su maná dentro; la
    cantidad del objeto abajo a la derecha de la casilla de abajo. Letras del atlas del bloque (kf4_cruz)."""
    import kf4_cruz as kc
    ph, pl = _hi_lo(PLAYER_STATE)
    fh, fl = _hi_lo(FX_TABLE)
    ih, il = _hi_lo(ITEM_COUNTS)
    xa, ya = kc.CASILLAS[2]
    xb, yb = kc.CASILLAS[3]
    cx = kc._hud(xa + kc.CASILLA_W // 2)
    y_nombre = kc._hud(ya - kc.LETRA_H - 2)            # encima de la casilla de arriba
    x_mana = kc._hud(xa + kc.CASILLA_W - 2)            # maná abajo a la derecha, "MP" abajo a la izquierda
    y_mana = kc._hud(ya + kc.CASILLA_H - kc.CIFRA_H - 2)
    x_mp = kc._hud(xa + 2)
    y_mp = kc._hud(ya + kc.CASILLA_H - kc.LETRA_H - 3)
    x_cant = kc._hud(xb + kc.CASILLA_W - 2)            # cantidad abajo a la derecha de la casilla de abajo
    y_cant = kc._hud(yb + kc.CASILLA_H - kc.CIFRA_H - 2)

    def color(reg, c):
        return [("lui", reg, c >> 16), ("ori", reg, reg, c & 0xFFFF)]
    p = [("addiu", "sp", "sp", -0x80), ("sd", "ra", 0x70, "sp"), ("sd", "s0", 0x40, "sp"), ("sd", "s1", 0x48, "sp"),
         ("sd", "s2", 0x50, "sp"), ("sd", "s3", 0x58, "sp"), ("sd", "s4", 0x60, "sp"),
         ("move", "s0", "a0"),
         ("jal", CURA_VA), ("move", "a0", "s0"),                # las fuentes que curan
         ("lbu", "a1", kc.OFF_TEXTO_TROZO, "s0"), ("addiu", "t0", "zero", 0xFF), ("beq", "a1", "t0", "salir"), ("nop",),
         ("jal", TABLA_SUBIR_UNA), ("addiu", "a0", "s0", kc.OFF_TABLA),
         ("lui", "s1", ph), ("addiu", "s1", "s1", pl),
         # ---- magia ----
         ("lbu", "t0", 0x3D, "s1"), ("beq", "t0", "zero", "objeto"), ("nop",),
         ("sltiu", "t1", "t0", 91), ("beq", "t1", "zero", "objeto"), ("nop",),
         ("sll", "t2", "t0", 8), ("sll", "t3", "t0", 4), ("addu", "t2", "t2", "t3"),
         ("lui", "t3", fh), ("addiu", "t3", "t3", fl), ("addu", "s2", "t2", "t3"),
         ("move", "s3", "zero"),
         "largo", ("sll", "t4", "s3", 1), ("addu", "t4", "s2", "t4"), ("lhu", "t5", 0, "t4"),
         ("ori", "t6", "zero", 0xFFFF), ("beq", "t5", "t6", "largo_fin"), ("nop",),
         ("andi", "t6", "t5", 0x8000), ("bne", "t6", "zero", "largo_fin"), ("nop",),
         ("addiu", "s3", "s3", 1), ("slti", "t6", "s3", 0x1A), ("bne", "t6", "zero", "largo"), ("nop",),
         "largo_fin", ("addiu", "t6", "zero", LETRA_W), ("mult", "s3", "t6"), ("nop",), ("nop",), ("mflo", "t7"),
         ("nop",), ("nop",), ("srl", "t7", "t7", 1), ("ori", "t8", "zero", cx), ("subu", "a1", "t8", "t7"),
         ("move", "a0", "s2"), ("ori", "a2", "zero", y_nombre), ("move", "a3", "zero")] + color("s4", COLOR_NOMBRE) + [
         ("jal", "cadena"), ("nop",),
         # maná: grande abajo a la derecha; "MP" pequeño abajo a la izquierda
         ("lhu", "a0", 0xFC, "s2"), ("ori", "a1", "zero", x_mana), ("ori", "a2", "zero", y_mana),
         ("addiu", "a3", "zero", 1)] + color("s4", COLOR_MANA) + [("jal", "numero"), ("nop",),
         ("addiu", "a0", "s0", kc.OFF_TEXTO_MP), ("ori", "a1", "zero", x_mp), ("ori", "a2", "zero", y_mp),
         ("move", "a3", "zero")] + color("s4", COLOR_MANA) + [("jal", "cadena"), ("nop",),
         # ---- cantidad del objeto del atajo ----
         "objeto", ("lbu", "t0", 0x48, "s1"), ("addiu", "t1", "zero", 1), ("bne", "t0", "t1", "salir"), ("nop",),
         ("lhu", "t0", 0x46, "s1"), ("sltiu", "t1", "t0", 32), ("beq", "t1", "zero", "salir"), ("nop",),
         ("lui", "t1", ih), ("addiu", "t1", "t1", il), ("addu", "t1", "t1", "t0"), ("lbu", "a0", 0, "t1"),
         ("beq", "a0", "zero", "salir"), ("nop",),
         ("ori", "a1", "zero", x_cant), ("ori", "a2", "zero", y_cant), ("addiu", "a3", "zero", 1)] + color("s4", COLOR_CANTIDAD) + [
         ("jal", "numero"), ("nop",),
         "salir", ("ld", "s4", 0x60, "sp"), ("ld", "s3", 0x58, "sp"), ("ld", "s2", 0x50, "sp"), ("ld", "s1", 0x48, "sp"),
         ("ld", "s0", 0x40, "sp"), ("ld", "ra", 0x70, "sp"), ("jr", "ra"), ("addiu", "sp", "sp", 0x80),
         # cadena(a0 = texto u16, a1 = x, a2 = y, a3 = grande); s4 = color
         "cadena", ("addiu", "sp", "sp", -0x40), ("sd", "ra", 0x30, "sp"), ("sd", "s5", 0x20, "sp"),
         ("sd", "s6", 0x10, "sp"), ("sd", "s7", 0, "sp"),
         ("move", "s5", "a0"), ("move", "s6", "a1"), ("addiu", "s7", "zero", 0x1A),
         "c_bucle", ("lhu", "t0", 0, "s5"), ("ori", "t1", "zero", 0xFFFF), ("beq", "t0", "t1", "c_fin"), ("nop",),
         ("andi", "t1", "t0", 0x8000), ("bne", "t1", "zero", "c_fin"), ("nop",),
         ("andi", "t1", "t0", 0x4000), ("bne", "t1", "zero", "c_sig"), ("nop",),
         ("sw", "a2", 0x28, "sp"), ("sw", "a3", 0x2C, "sp"),
         ("andi", "a0", "t0", 0xFF), ("jal", "glifo"), ("move", "a1", "s6"),
         ("lw", "a2", 0x28, "sp"), ("lw", "a3", 0x2C, "sp"),
         ("addiu", "s6", "s6", LETRA_W), ("beq", "a3", "zero", "c_sig"), ("nop",),
         ("addiu", "s6", "s6", LETRA_GW - LETRA_W),
         "c_sig", ("addiu", "s5", "s5", 2), ("addiu", "s7", "s7", -1), ("bne", "s7", "zero", "c_bucle"), ("nop",),
         "c_fin", ("ld", "s7", 0, "sp"), ("ld", "s6", 0x10, "sp"), ("ld", "s5", 0x20, "sp"), ("ld", "ra", 0x30, "sp"),
         ("jr", "ra"), ("addiu", "sp", "sp", 0x40),
         # numero(a0 = valor, a1 = x del borde derecho, a2 = y, a3 = grande); s4 = color
         "numero", ("addiu", "sp", "sp", -0x40), ("sd", "ra", 0x30, "sp"), ("sd", "s5", 0x20, "sp"),
         ("sd", "s6", 0x10, "sp"), ("sd", "s7", 0, "sp"),
         ("move", "s5", "a0"), ("move", "s6", "a1"), ("sw", "a2", 0x28, "sp"), ("sw", "a3", 0x2C, "sp"),
         ("addiu", "s7", "zero", LETRA_W), ("beq", "a3", "zero", "n_bucle"), ("nop",), ("addiu", "s7", "zero", LETRA_GW),
         "n_bucle", ("addiu", "t1", "zero", 10), ("div", "s5", "t1"), ("nop",), ("nop",), ("mflo", "s5"), ("mfhi", "t0"),
         ("nop",), ("nop",), ("subu", "s6", "s6", "s7"),
         ("addiu", "a0", "t0", 0x10), ("move", "a1", "s6"), ("lw", "a2", 0x28, "sp"), ("jal", "glifo"), ("lw", "a3", 0x2C, "sp"),
         ("bne", "s5", "zero", "n_bucle"), ("nop",),
         ("ld", "s7", 0, "sp"), ("ld", "s6", 0x10, "sp"), ("ld", "s5", 0x20, "sp"), ("ld", "ra", 0x30, "sp"),
         ("jr", "ra"), ("addiu", "sp", "sp", 0x40),
         # glifo(a0 = código, a1 = x, a2 = y, a3 = grande): sombra y letra; s0 = bloque, s4 = color
         # pequeña: (u, v) del mapa, celda LETRA_W x LETRA_H téxeles; grande (solo cifras): fila de cifras del atlas
         "glifo", ("bne", "a3", "zero", "g_grande"), ("nop",),
         ("sll", "t0", "a0", 1), ("addu", "t0", "t0", "s0"), ("lbu", "t1", kc.OFF_TEXTO_MAPA, "t0"),
         ("addiu", "t2", "zero", 0xFF), ("beq", "t1", "t2", "g_nada"), ("nop",),
         ("lbu", "t2", kc.OFF_TEXTO_MAPA + 1, "t0"),
         ("addiu", "t4", "zero", kc.LETRA_W), ("beq", "zero", "zero", "g_ok"), ("addiu", "t5", "zero", kc.LETRA_H),
         "g_grande", ("addiu", "t1", "a0", -0x10), ("sltiu", "t0", "t1", 10), ("beq", "t0", "zero", "g_nada"), ("nop",),
         ("sll", "t0", "t1", 3), ("addu", "t1", "t0", "t1"),           # u = cifra * 9
         ("addiu", "t2", "zero", kc.CIFRA_V), ("addiu", "t4", "zero", kc.CIFRA_W), ("addiu", "t5", "zero", kc.CIFRA_H),
         "g_ok", ("addiu", "sp", "sp", -0x80), ("sd", "ra", 0x70, "sp"), ("sd", "s5", 0x60, "sp"),
         ("andi", "a1", "a1", 0xFFF0), ("andi", "a2", "a2", 0xFFF0),   # en píxeles enteros: un téxel por píxel
         ("sw", "a1", 0x50, "sp"), ("sw", "a2", 0x54, "sp"), ("sll", "t4", "t4", 4), ("sw", "t4", 0x58, "sp"),
         ("sll", "t5", "t5", 4), ("sw", "t5", 0x5C, "sp"),
         ("sw", "t1", 0x68, "sp"), ("sw", "t2", 0x6C, "sp"),
         ("move", "s5", "zero"),                                   # 0 sombra, 1 letra
         "g_pasada", ("ld", "t6", kc.OFF_TEXTO_TEX, "s0"), ("sd", "t6", 0x00, "sp"),
         ("ld", "t6", kc.OFF_TEXTO_TEX + 8, "s0"), ("sd", "t6", 0x08, "sp"),
         ("addiu", "t6", "zero", 0x156), ("sw", "t6", 0x10, "sp"),
         ("lw", "t7", 0x50, "sp"), ("lw", "t8", 0x54, "sp")] + color("t6", COLOR_SOMBRA) + [
         ("bne", "s5", "zero", "g_color"), ("nop",),
         ("addiu", "t7", "t7", 16), ("beq", "zero", "zero", "g_puesto"), ("addiu", "t8", "t8", 16),
         "g_color", ("move", "t6", "s4"),
         "g_puesto", ("sw", "t6", 0x14, "sp"),
         ("sh", "t7", 0x20, "sp"), ("sh", "t8", 0x22, "sp"), ("sw", "zero", 0x24, "sp"),
         ("lw", "t1", 0x68, "sp"), ("lw", "t2", 0x6C, "sp"),
         ("sll", "t3", "t1", 4), ("sw", "t3", 0x28, "sp"), ("sll", "t3", "t2", 4), ("sw", "t3", 0x2C, "sp"),
         ("lw", "t4", 0x58, "sp"), ("lw", "t5", 0x5C, "sp"),
         ("addu", "t3", "t7", "t4"), ("sh", "t3", 0x30, "sp"), ("addu", "t3", "t8", "t5"), ("sh", "t3", 0x32, "sp"),
         ("sw", "zero", 0x34, "sp"),
         ("sll", "t3", "t1", 4), ("addu", "t3", "t3", "t4"), ("sw", "t3", 0x38, "sp"),   # t4, t5: celda * 16
         ("sll", "t3", "t2", 4), ("addu", "t3", "t3", "t5"), ("sw", "t3", 0x3C, "sp"),
         ("jal", SPRITE_TEXTURADO), ("move", "a0", "sp"),
         ("addiu", "s5", "s5", 1), ("slti", "t0", "s5", 2), ("bne", "t0", "zero", "g_pasada"), ("nop",),
         ("ld", "s5", 0x60, "sp"), ("ld", "ra", 0x70, "sp"), ("addiu", "sp", "sp", 0x80),
         "g_nada", ("jr", "ra"), ("nop",)]
    code = _ensamblar(p, TEXTO_VA)
    assert len(code) <= TEXTO_FIN - TEXTO_VA, len(code)
    return code + bytes(TEXTO_FIN - TEXTO_VA - len(code))


# ======================= EXP del arma en la pantalla de equipo (menú) =======================
# La página del arma (menu/equip_a_para.dat) es una lista de sprites de 0x60 bytes: palabras de la tabla del
# juego, números y rectángulos con textura. Se le añade, bajo "Dura", una fila: la palabra "Exp", una barra que
# se llena y "Level" con el nivel del arma (el número 74, el mismo que el "Level" de arriba).
# La barra es el sprite de las barras de volumen (menu/option_para.dat, el manejador 22 MenuSprite_SizeToLevel,
# que estira el sprite tantos píxeles como diga su hueco 0-2). Se le enseña un hueco nuevo, el 3: la experiencia
# del arma que se está mirando (equip_list_shown[0]->item->item_number - 150 en weapon_level_records).
TAMANO_A_NIVEL_GANCHO = 0x204664                 # b 0x204690 (hueco que no es 0, 1 ni 2: nivel 0x7F)
TAMANO_A_NIVEL_ORIG = bytes.fromhex("0a00001040100500")
TAMANO_A_NIVEL_VUELTA = 0x20468C                 # sll v0, a1, 1 y sigue con a1 = nivel
EXP_HUECO_VA, EXP_HUECO_FIN = 0x1AEAF8, 0x1AED10  # Debug_MarkCursorLine y Debug_EditInt: nada los llama
EXP_HUECO_FIRMA = bytes.fromhex("b0ffbd272000b2ff1000b1ff2d908000")
EQUIP_LIST_SHOWN = 0x5D5480
EXP_BARRA_ANCHO = 96                             # píxeles de la barra llena
EXP_HUECO_BARRA = 3
# Usos para subir de nivel un arma (Player_CountWeaponUse): el juego pide 180 y 480; aquí, 70 y 70 más
EXP_NIVEL2, EXP_NIVEL3 = 70, 140
EXP_GANCHOS = ((0x1BA720, 0x2C6201E0, 0x2C620000), (0x1BA72C, 0x240300B4, 0x24030000),
               (0x1BA73C, 0x240201E0, 0x24020000))      # sltiu v0,v1,480 / addiu v1,zero,180 / addiu v0,zero,480


def codigo_exp_menu(rapida=True):
    N2, N3 = (EXP_NIVEL2, EXP_NIVEL3) if rapida else (180, 480)
    rh, rl = _hi_lo(REGISTROS_ARMA)
    eh, el = _hi_lo(EQUIP_LIST_SHOWN)
    W = EXP_BARRA_ANCHO

    def escala(reg_usos, den):     # a1 = reg_usos * W / den
        return [("addiu", "t5", "zero", W), ("mult", reg_usos, "t5"), ("nop",), ("nop",), ("mflo", "t5"),
                ("nop",), ("nop",), ("addiu", "t6", "zero", den), ("div", "t5", "t6"), ("nop",), ("nop",),
                ("mflo", "a1"), ("nop",), ("nop",)]
    prog = [("addiu", "t0", "zero", EXP_HUECO_BARRA), ("bne", "a0", "t0", "vuelta"), ("nop",),
            ("lui", "t0", eh), ("lw", "t0", el, "t0"), ("beq", "t0", "zero", "cero"), ("nop",),
            ("lw", "t0", 0, "t0"), ("beq", "t0", "zero", "cero"), ("nop",),
            ("lh", "t1", 0xC, "t0"), ("addiu", "t1", "t1", -150),
            ("sltiu", "t2", "t1", 70), ("beq", "t2", "zero", "cero"), ("nop",),
            ("sll", "t2", "t1", 5), ("sll", "t3", "t1", 1), ("addu", "t2", "t2", "t3"),
            ("lui", "t3", rh), ("addiu", "t3", "t3", rl), ("addu", "t2", "t2", "t3"),
            ("lhu", "t4", 0x16, "t2"),                                   # usos del arma
            ("slti", "t0", "t4", N2), ("beq", "t0", "zero", "nivel2"), ("nop",)]
    prog += escala("t4", N2) + [("j", TAMANO_A_NIVEL_VUELTA), ("nop",),
                                 "nivel2", ("slti", "t0", "t4", N3), ("beq", "t0", "zero", "lleno"), ("nop",),
                                 ("addiu", "t4", "t4", -N2)]
    prog += escala("t4", N3 - N2) + [("j", TAMANO_A_NIVEL_VUELTA), ("nop",),
                                 "lleno", ("addiu", "a1", "zero", W), ("j", TAMANO_A_NIVEL_VUELTA), ("nop",),
                                 "cero", ("addiu", "a1", "zero", 0),
                                 "vuelta", ("j", TAMANO_A_NIVEL_VUELTA), ("nop",)]
    code = _ensamblar(prog, EXP_HUECO_VA)
    assert len(code) <= EXP_HUECO_FIN - EXP_HUECO_VA, len(code)
    return code + bytes(EXP_HUECO_FIN - EXP_HUECO_VA - len(code))


def _para_registros(d):
    tot = struct.unpack_from("<I", d, 0)[0]
    return [bytearray(d[0x10 + k * 0x60:0x10 + (k + 1) * 0x60]) for k in range((tot - 0x10) // 0x60)]


def _para_bytes(regs, cabecera):
    cuerpo = b"".join(bytes(r) for r in regs)
    out = bytearray(cabecera[:0x10]) + cuerpo
    struct.pack_into("<I", out, 0, len(out))
    return bytes(out)


def _y(r):
    return struct.unpack_from("<H", r, 2)[0]


def _mover(r, dy):
    for o in (2, 0x12):
        struct.pack_into("<H", r, o, struct.unpack_from("<H", r, o)[0] + dy)


def _caja(r, x0, y0, x1, y1):
    struct.pack_into("<HH", r, 0, x0 * 16, y0 * 16)
    struct.pack_into("<HH", r, 0x10, x1 * 16, y1 * 16)


def para_arma_con_exp(d_equip_a, d_option):
    """equip_a_para.dat con la fila de experiencia; None si el archivo no es el que se espera."""
    regs = _para_registros(d_equip_a)
    if any(r[0x31] == 1 and r[0x32] == 8 for r in regs):     # ya tiene "Exp"
        return None
    dura = next((r for r in regs if r[0x31] == 1 and r[0x32] == 141), None)
    nivel = next((r for r in regs if r[0x31] == 2 and struct.unpack_from("<i", r, 0x34)[0] == 74), None)
    palabra_nivel = next((r for r in regs if r[0x31] == 1 and r[0x32] == 9), None)
    barra = next((r for r in _para_registros(d_option) if r[0x31] == 0 and r[0x3E] == 22), None)
    if not (dura and nivel and palabra_nivel and barra):
        return None
    yd = _y(dura)                                  # en 12.4
    paso = 12 * 16
    for r in regs:                                 # Weight, Length y Dura suben 5 píxeles
        if _y(r) in (yd, yd - paso, yd - 2 * paso):
            _mover(r, -5 * 16)
    fila = yd // 16 - 5 + 11                       # la fila nueva, debajo de Dura
    nuevos = []
    w = bytearray(dura); w[0x32] = 8; _caja(w, 1790, fila, 1820, fila + 10); nuevos.append(w)      # "Exp"
    for tinte, manejador in (((34, 30, 26, 128), 0), ((128, 128, 128, 128), 22)):                  # fondo y relleno
        b = bytearray(dura)
        b[0:0x30] = barra[0:0x30]                  # textura y UV del sprite de volumen
        b[4:8] = dura[4:8]                         # la profundidad, la de los textos de esta página
        b[0x14:0x18] = dura[0x14:0x18]
        b[0x31] = 0
        b[0x20:0x24] = bytes(tinte)
        _caja(b, 1826, fila + 1, 1826 + EXP_BARRA_ANCHO, fila + 9)
        struct.pack_into("<f", b, 0x18, 1.0)
        b[0x3E] = manejador
        b[0x3F] = EXP_HUECO_BARRA if manejador == 22 else 0
        nuevos.append(b)
    pl = bytearray(palabra_nivel); _caja(pl, 1930, fila, 1980, fila + 10); nuevos.append(pl)        # "Level"
    nm = bytearray(nivel); _caja(nm, 1972, fila, 2012, fila + 10); nuevos.append(nm)                # el nivel
    return _para_bytes(regs + nuevos, d_equip_a)


def parchear_ejecutable(elf, giro, log, mando="dos_sticks", vida_numero=True, cruz=True, exp_menu=True, cruz_off=None,
                        escalon=True):
    """Devuelve el ejecutable con el giro multiplicado y el mando cambiado. Siempre parte del original.
    mando: 'dos_sticks', 'dos_sticks_invertido' u 'original'."""
    e = bytearray(elf)
    con_mando = bool(mando and mando != "original" and
                     bytes(e[LEER_MANDO_VA - 0xFF000:LEER_MANDO_VA - 0xFF000 + len(LEER_MANDO_FIRMA)]) == LEER_MANDO_FIRMA)
    fc = CRUZ_HUECO_VA - 0xFF000
    cruz = bool(cruz and vida_numero and con_mando and bytes(e[fc:fc + len(CRUZ_HUECO_FIRMA)]) == CRUZ_HUECO_FIRMA)
    if vida_numero:
        fo, fg = VIDA_HUECO_VA - 0xFF000, VIDA_GANCHO_VA - 0xFF000
        fb = BARRA_HUECO_VA - 0xFF000
        if bytes(e[fo:fo + 16]) == VIDA_HUECO_FIRMA and struct.unpack_from("<I", e, fg)[0] == VIDA_GANCHO_ORIG \
                and bytes(e[fb:fb + 16]) == BARRA_HUECO_FIRMA:
            if cruz_off:      # cifras con la fuente del menú del juego (van en el bloque de 099.map)
                e[fo:fo + VIDA_HUECO_FIN - VIDA_HUECO_VA] = codigo_vida_textura(cruz, cruz_off)
            else:
                e[fo:fo + VIDA_HUECO_FIN - VIDA_HUECO_VA] = codigo_vida(cruz)
            if cruz:
                fm, ft, fg3 = MAGIA_VA - 0xFF000, TEXTO_VA - 0xFF000, GANCHO_BRAZOS_VA - 0xFF000
                con_magia = bytes(e[fm:fm + 8]) == MAGIA_FIRMA and bytes(e[ft:ft + 8]) == TEXTO_FIRMA and \
                    struct.unpack_from("<I", e, fg3)[0] == (3 << 26) | (CARGAR_BRAZOS >> 2)
                if con_magia:
                    cod_m, gancho = codigo_magia()
                    e[fm:fm + MAGIA_FIN - MAGIA_VA] = cod_m
                    e[ft:ft + TEXTO_FIN - TEXTO_VA] = codigo_texto()
                    struct.pack_into("<I", e, fg3, (3 << 26) | (gancho >> 2))
                    log.append("Cruz: arriba la magia (nombre encima y maná dentro), abajo el objeto con su cantidad")
                else:
                    log.append("AVISO: no reconozco los huecos para la magia de la cruz; sin magia ni cantidades")
                e[fc:fc + CRUZ_HUECO_FIN - CRUZ_HUECO_VA] = codigo_cruz(con_magia)
                e[fb:fb + BARRA_HUECO_FIN - BARRA_HUECO_VA] = codigo_dibujo_cruz(cruz_off or 0, con_magia)
                log.append("Cruz de equipo: derecha arma, izquierda escudo, arriba magia, abajo consumible"
                           + ("" if cruz_off else " (sin ilustraciones: no las encontré en el mapa)"))
            struct.pack_into("<I", e, fg, (3 << 26) | (VIDA_HUECO_VA >> 2))
            log.append("HUD: vida en número dentro del orbe")
        else:
            log.append("AVISO: este ejecutable no es el SLES_509.20 que conozco; HUD sin cambiar")
    if exp_menu:
        fx, fg2 = EXP_HUECO_VA - 0xFF000, TAMANO_A_NIVEL_GANCHO - 0xFF000
        if bytes(e[fx:fx + 16]) == EXP_HUECO_FIRMA and bytes(e[fg2:fg2 + 8]) == TAMANO_A_NIVEL_ORIG:
            rapida = all(struct.unpack_from("<I", e, va - 0xFF000)[0] == orig for va, orig, _ in EXP_GANCHOS)
            e[fx:fx + EXP_HUECO_FIN - EXP_HUECO_VA] = codigo_exp_menu(rapida)
            if rapida:
                for (va, orig, base), n in zip(EXP_GANCHOS, (EXP_NIVEL3, EXP_NIVEL2, EXP_NIVEL3)):
                    struct.pack_into("<I", e, va - 0xFF000, base | n)
                log.append(f"Armas: suben de nivel a los {EXP_NIVEL2} y {EXP_NIVEL3} golpes (antes 180 y 480)")
            struct.pack_into("<II", e, fg2, (2 << 26) | (EXP_HUECO_VA >> 2), 0)
            log.append("Menú: barra de experiencia del arma en la pantalla de equipo")
        else:
            log.append("AVISO: no reconozco la función de las barras del menú; sin barra de experiencia")
    if mando and mando != "original":
        fo = LEER_MANDO_VA - 0xFF000
        if bytes(e[fo:fo + len(LEER_MANDO_FIRMA)]) == LEER_MANDO_FIRMA:
            e[fo:fo + LEER_MANDO_FIN - LEER_MANDO_VA] = codigo_mando(mando.endswith("invertido"), cruz)
            log.append("Mando: stick izquierdo andar + paso lateral, stick derecho girar + mirar"
                       + (" (vertical invertido)" if mando.endswith("invertido") else ""))
        else:
            log.append("AVISO: este ejecutable no es el SLES_509.20 que conozco; mando sin cambiar")
    if escalon:           # (solo para los mapas portados: sus escalones de casilla son de 0,78 y 1,25 m)
        parche_escalon(e, log)
    if giro and abs(giro - 1.0) > 1e-6:
        hechos = 0
        for tabla, factor in ((GIRO_TOP, giro), (GIRO_GAIN, giro), (GIRO_LOSS, max(1.0, giro * 1.15))):
            pat = struct.pack(f"<{len(tabla)}f", *tabla)
            i = bytes(e).find(pat)
            if i < 0:
                log.append("AVISO: no encontré una tabla de giro en el ejecutable; giro sin cambiar")
                return bytes(e)
            struct.pack_into(f"<{len(tabla)}f", e, i, *[v * factor for v in tabla])
            hechos += 1
        log.append(f"Giro de cámara x{giro:g} ({hechos} tablas del ejecutable)")
    return bytes(e)


def _leer_dat(path, lang, nombre):
    """(tabla del DAT, bytes del archivo) de un archivo interno de ese idioma, o (tabla, None)."""
    dat_off, tab = _dat_table(path, lang)
    if tab is None:
        return None, None
    ent = tab.get(nombre) or tab.get(nombre.replace("/", "\\"))
    if ent is None:
        return tab, None
    with open(path, "rb") as f:
        f.seek(dat_off + ent[3])
        return tab, f.read(ent[1])


# equipo al empezar (claves item_NNN=cantidad del ini de Partida nueva, core/ini.c: Ini_SetItem; las armas son
# 150-219 y lo que se lleva puesto 220-379, cada grupo empieza por su "nada")
INI_ARMAS = list(range(151, 163))              # 12 armas
INI_ESCUDOS = list(range(221, 230))            # 9 escudos
INI_OBJETOS = {6: 9, 7: 5, 8: 5, 13: 3, 145: 30}   # hierbas, líquido de hierbas, fruta del bosque, flor de dragón, flechas
INI_RESUMEN = (f"{len(INI_ARMAS)} armas, {len(INI_ESCUDOS)} escudos y "
               + ", ".join(f"{n} del objeto {k}" for k, n in INI_OBJETOS.items()))


INI_PARTIDA = "ini/0611.ini"   # el que lee Partida nueva
EQUIPO_TXT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "equipo_inicial.txt")
_CLAVES_INI = ("item_", "magic_", "equip_", "hp=", "mp=", "power=", "magic=", "level=", "exp=", "gold=")


# Daño de los enemigos: cada golpe cuerpo a cuerpo (chr.prm, 0x450 bytes por registro; EntityParams.melee_attacks:
# 3 ataques de 0x88 en +0x240, cada uno con 3 partes de 0x28 desde +0x10 y su fuerza por elemento, 9 x s16) hace
# sum(f² / (f + 1,3 x defensa + (fuerza del jugador + 1) / 3)) (Attack_StrengthDamageToPlayer). Al principio, con 50
# de vida, la serpiente (50 + 50) mataba de un golpe. Se escalan las fuerzas de cada parte para que, al jugador
# del principio (defensa ~5, fuerza 20), no le quiten más de DANO_MAX_GOLPE.
DANO_MAX_GOLPE = 10
BARRIL_DUREZA = 8         # daño de un golpe que rompe el barril (obj.prm def 2; el juego pide 181)
DANO_DEFENSA, DANO_FUERZA = 5.0, 20.0


def _dano(fuerzas):
    c = 1.3 * DANO_DEFENSA + (DANO_FUERZA + 1) / 3
    return sum(f * f / (f + c) for f in fuerzas if f > 0)


DANO_SOLO_TIPOS = {21}    # solo la serpiente (chr.prm byte 0x02: 21 = Snake); los demás enemigos quitan lo suyo


def rebajar_dano(d):
    b = bytearray(d)
    n = 0
    for r in range(len(b) // 0x450):
        if b[r * 0x450 + 2] not in DANO_SOLO_TIPOS:
            continue
        for a in range(3):
            o = r * 0x450 + 0x240 + a * 0x88
            for j in range(3):
                p = o + 0x10 + j * 0x28
                if p + 18 > len(b):
                    continue
                fs = list(struct.unpack_from("<9h", b, p))
                if _dano(fs) <= DANO_MAX_GOLPE:
                    continue
                lo, hi = 0.0, 1.0                      # escala que deja el daño justo en DANO_MAX_GOLPE
                for _ in range(30):
                    k = (lo + hi) / 2
                    if _dano([f * k for f in fs]) > DANO_MAX_GOLPE:
                        hi = k
                    else:
                        lo = k
                struct.pack_into("<9h", b, p, *[max(1, round(f * lo)) if f > 0 else f for f in fs])
                n += 1
    return bytes(b), n


def lineas_equipo():
    """Las líneas del ini que se añaden a Partida nueva: las de equipo_inicial.txt (sin comentarios) si existe; si
    no, las de INI_ARMAS / INI_ESCUDOS / INI_OBJETOS. Devuelve (lineas, resumen)."""
    global INI_RESUMEN
    if os.path.isfile(EQUIPO_TXT):
        lineas = []
        for ln in open(EQUIPO_TXT, encoding="utf-8", errors="replace"):
            ln = ln.split("#", 1)[0].strip().replace(" ", "")
            if "=" in ln and ln.startswith(_CLAVES_INI):
                lineas.append(ln.encode("ascii", "ignore"))
        it = [l for l in lineas if l.startswith(b"item_")]
        armas = sum(1 for l in it if 150 <= int(l[5:8] or 0) < 220)
        puesto = sum(1 for l in it if int(l[5:8] or 0) >= 220)
        mag = sum(1 for l in lineas if l.startswith(b"magic_"))
        INI_RESUMEN = (f"equipo_inicial.txt: {armas} armas, {puesto} escudos/armaduras, {len(it) - armas - puesto} "
                       f"objetos, {mag} magias")
        return lineas, INI_RESUMEN
    lineas = [b"item_%03d=1" % k for k in INI_ARMAS + INI_ESCUDOS]
    lineas += [b"item_%03d=%d" % (k, n) for k, n in INI_OBJETOS.items()]
    return lineas, INI_RESUMEN


def ini_con_equipo(texto):
    """El ini original sin comentarios (en CR LF: Ini_ReadLine solo corta ahí, y una línea de más de 0x400 bytes
    se sale de su búfer) y detrás las líneas del equipo, que mandan sobre las del original."""
    fin = b"\r\n"
    base = []
    for ln in texto.replace(b"\x00", b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n"):
        ln = ln.split(b";", 1)[0].strip()
        if b"=" in ln:
            base.append(ln)
    lineas, _ = lineas_equipo()
    return fin.join(base + lineas) + fin


def patch_iso(iso, new_map, log, debug_ini=None, giro=1.0, mando="dos_sticks", vida_numero=True, cruz=True, exp_menu=True,
              pulpo=None):
    """Copia la ISO una vez a '(valle).iso' y en las siguientes veces solo reescribe lo que cambia.
    debug_ini: '9999' etc. para que Partida nueva use ese ini de desarrollo; None = el normal."""
    base, ext = os.path.splitext(iso)
    out = f"{base} (valle){ext}"
    if os.path.isfile(out) and os.path.getsize(out) >= os.path.getsize(iso):
        print(f"Actualizando {os.path.basename(out)} (sin volver a copiar la ISO)...")
    else:
        print(f"Copiando ISO -> {os.path.basename(out)} (solo la primera vez, tarda un poco)...")
        shutil.copyfile(iso, out)
    # ejecutable: se copia el original y se le aplican los parches (así cambiar GIRO siempre funciona)
    s0 = md.Source(iso)
    exe = next((k for k in s0.iso_files if k.startswith(("SLES_", "SLUS_", "SCES_", "SLPS_"))), None)
    if exe:
        off, size = s0.iso_files[exe]
        with open(iso, "rb") as f:
            f.seek(off)
            elf = f.read(size)
        import kf4_cruz
        i_cruz = new_map.find(kf4_cruz.FIRMA)
        nuevo = parchear_ejecutable(elf, giro, log, mando, vida_numero, cruz, exp_menu,
                                    i_cruz if i_cruz >= 0 and i_cruz % 16 == 0 else None)
        with open(out, "r+b") as f:
            f.seek(off)
            f.write(nuevo)
    done = 0
    # un mapa más grande que su hueco del DAT va al final de la ISO: el juego abre los archivos del DAT por
    # sector (inicio del DAT + offset / 2048, KF_File_Open) y no mira dónde acaba el DAT
    fin_original = (os.path.getsize(iso) + 2047) // 2048 * 2048
    _, tab0 = _dat_table(iso, "SPA")
    hueco0 = min((t["099.map"][2] for t in [tab0] if t), default=0)
    grande = len(new_map) > hueco0
    # el pulpo (kf4_pulpo): su .chr va detrás del mapa grande (o solo, si el mapa cabe en su hueco) y el registro
    # chr/c0037.chr (vacío en el juego) apunta allí
    chr_pulpo = pulpo[0] if pulpo else None
    n_mapa = (len(new_map) + 2047) // 2048 * 2048 if grande else 0
    n_pulpo = (len(chr_pulpo) + 2047) // 2048 * 2048 if chr_pulpo else 0
    if len(new_map) > MAPA_MAXIMO:
        raise RuntimeError(f"El mapa nuevo ({len(new_map)} bytes) pasa de lo que el juego carga ({MAPA_MAXIMO}) "
                           f"aun quitando caras: este nivel todavía es demasiado grande")
    # sitio del mapa grande, por idioma: dentro de su propio DAT, encima de mapas seguidos que este mod no usa
    # (el DAT está entero por debajo de los 4 GB y el juego lo lee seguro); si no hay hueco, DUMMY.OUT (relleno de
    # 512 MB); y si tampoco, al final de la ISO (más allá de los 4 GB el lector de la PS2 se cuelga)
    destinos = {}
    destinos_pulpo = {}

    def buscar_en_dat(tabo, n, ocupados):
        """(offset en el DAT, nombres) de mapas seguidos que este mod no usa con n bytes, o None."""
        ents = sorted(((v[3], v[2], k) for k, v in tabo.items()), key=lambda e: e[0])
        # ni los vecinos de 099 (0, 4, 5, 8, 98) ni los primeros mapas: se cogen los de número más alto
        libre = lambda k: (k.endswith(".map") and len(k) == 7 and k[:3].isdigit()
                           and int(k[:3]) > 10 and int(k[:3]) not in (98, 99) and k not in ocupados)
        orden = sorted(range(len(ents)), key=lambda a: -int(ents[a][2][:3]) if libre(ents[a][2]) else 0)
        for a in orden:
            if not libre(ents[a][2]):
                continue
            b = a
            while b < len(ents) and libre(ents[b][2]):
                if ents[b][0] + ents[b][1] - ents[a][0] >= n:
                    return ents[a][0], [e[2] for e in ents[a:b + 1]]
                if b + 1 < len(ents) and ents[b + 1][0] != ents[b][0] + ents[b][1]:
                    break
                b += 1
        return None

    for lg in ("SPA", "ENG", "FRA", "GER", "ITA"):
        d_off, tabo = _dat_table(iso, lg)
        if not tabo:
            continue
        usados = []
        dummy_libre = 0
        c = s0.iso_files.get("DUMMY.OUT")
        if grande:
            m = buscar_en_dat(tabo, n_mapa, set())
            if m and d_off + m[0] + n_mapa < (1 << 32):
                destinos[lg] = (d_off + m[0], f"en su DAT, encima de {', '.join(m[1])}")
                usados = m[1]
            elif c and c[1] >= n_mapa and c[0] >= d_off and c[0] + n_mapa < (1 << 32):
                destinos[lg] = (c[0], "dentro de DUMMY.OUT")
                dummy_libre = n_mapa
            else:
                destinos[lg] = (fin_original, "al final de la ISO (más allá de los 4 GB: puede colgarse)")
        if chr_pulpo:
            # el pulpo aparte del mapa (así el mapa sigue yendo donde iba), y nunca más allá de los 4 GB
            m = buscar_en_dat(tabo, n_pulpo, set(usados))
            if m and d_off + m[0] + n_pulpo < (1 << 32):
                destinos_pulpo[lg] = (d_off + m[0], f"en su DAT, encima de {', '.join(m[1])}")
            elif c and c[1] >= dummy_libre + n_pulpo and c[0] >= d_off and c[0] + dummy_libre + n_pulpo < (1 << 32):
                destinos_pulpo[lg] = (c[0] + dummy_libre, "dentro de DUMMY.OUT")
    if chr_pulpo and not destinos_pulpo:
        log.append("AVISO: no hay sitio seguro para el modelo del pulpo: van serpientes en su lugar")
    with open(out, "r+b") as f:
        f.truncate(fin_original)
        if grande:
            for pos in sorted({d for d, _ in destinos.values()}):
                f.seek(pos)
                f.write(new_map + bytes((-len(new_map)) % 2048))
        for pos in sorted({d for d, _ in destinos_pulpo.values()}):
            f.seek(pos)
            f.write(chr_pulpo + bytes((-len(chr_pulpo)) % 2048))
        total = f.seek(0, 2)
        f.seek(16 * 2048 + 80)            # tamaño del volumen (descriptor primario), por si algo lo mira
        f.write(struct.pack("<I", total // 2048) + struct.pack(">I", total // 2048))
    if grande:
        log.append(f"Mapa de {len(new_map) // 1024} KB: no cabe en su hueco del DAT ({hueco0 // 1024} KB)")
        for lg, (pos, donde) in destinos.items():
            log.append(f"  {lg}: {donde} (byte {pos} de la ISO)")
    if destinos_pulpo:
        log.append(f"Pulpo: chr/c{kf4_pulpo.MODELO_PULPO:04d}.chr de {len(chr_pulpo) // 1024} KB")
        for lg, (pos, donde) in destinos_pulpo.items():
            log.append(f"  {lg}: {donde} (byte {pos} de la ISO)")
    for lang in ("SPA", "ENG", "FRA", "GER", "ITA"):
        dat_off, tab = _dat_table(out, lang)
        if tab is None:
            continue
        _, orig = _dat_table(iso, lang)
        with open(out, "r+b") as f:
            rec, _, alloc, off = orig["099.map"]
            if grande:
                f.seek(rec + 0x34)
                f.write(struct.pack("<III", len(new_map), (len(new_map) + 2047) // 2048 * 2048,
                                    destinos[lang][0] - dat_off))
            else:
                f.seek(dat_off + off)
                f.write(new_map + bytes(alloc - len(new_map)))
                f.seek(rec + 0x34)
                f.write(struct.pack("<III", len(new_map), alloc, off))
            nombre_pulpo = f"chr/c{kf4_pulpo.MODELO_PULPO:04d}.chr"
            if chr_pulpo and nombre_pulpo in orig and lang in destinos_pulpo:
                f.seek(orig[nombre_pulpo][0] + 0x34)
                f.write(struct.pack("<III", len(chr_pulpo), n_pulpo, destinos_pulpo[lang][0] - dat_off))
            elif nombre_pulpo in orig:
                f.seek(orig[nombre_pulpo][0] + 0x34)
                f.write(struct.pack("<III", *orig[nombre_pulpo][1:4]))
            # ini de arranque. Partida nueva lee ini/0611.ini (main: GameLoop_ResetSystems(0x263); el 9999 solo si
            # falta). Se parte del original (o del de debug) y se le añade el equipo; va en el hueco del 0611 o, si
            # no cabe, en el de otro ini de desarrollo que el juego nunca lee, y el registro del 0611 apunta allí.
            if INI_PARTIDA in orig:
                # siempre el de Partida nueva: el 9999 de depuración pone nivel 90 y otras cosas (sus claves debug_*
                # no hacen nada en el juego final); el equipo y lo demás, en equipo_inicial.txt
                src_ini = INI_PARTIDA
                if src_ini not in orig:
                    raise RuntimeError(f"No existe {src_ini}")
                _, s2, a2, o2 = orig[src_ini]
                with open(iso, "rb") as g:
                    g.seek(dat_off + o2)
                    texto = g.read(s2)
                nuevo_ini = ini_con_equipo(texto)
                huecos = [INI_PARTIDA] + sorted((k for k in orig if k.startswith("ini/") and k.endswith(".ini")
                                                 and k not in (INI_PARTIDA, "ini/9999.ini")),
                                                key=lambda k: orig[k][2])
                sitio = next((k for k in huecos if orig[k][2] >= len(nuevo_ini)), None)
                if sitio:
                    _, _, a3, o3 = orig[sitio]
                    f.seek(dat_off + o3)
                    f.write(nuevo_ini + bytes(a3 - len(nuevo_ini)))
                    f.seek(orig[INI_PARTIDA][0] + 0x34)
                    f.write(struct.pack("<III", len(nuevo_ini), a3, o3))
                    if done == 0:
                        log.append(f"Partida nueva ({INI_PARTIDA}, {len(nuevo_ini)} bytes en el hueco de {sitio}) "
                                   f"con equipo: {INI_RESUMEN}")
                else:
                    f.seek(orig[INI_PARTIDA][0] + 0x34)
                    f.write(struct.pack("<III", s2, a2, o2))
                    log.append("AVISO: el ini con el equipo no cabe en ningún hueco; Partida nueva sin equipo extra")
                # el 0001 de versiones anteriores de este parche: se deja como el original
                if "ini/0001.ini" in orig:
                    f.seek(orig["ini/0001.ini"][0] + 0x34)
                    f.write(struct.pack("<III", *orig["ini/0001.ini"][1:4]))
            elif done == 0:
                log.append(f"AVISO: no encuentro {INI_PARTIDA}; Partida nueva sin equipo extra")
            # el barril que se rompe (obj.prm def 2): pide 181 de daño de un golpe (MapObjectDefHalves.toughness),
            # con el arma del principio no se rompía nunca; se baja a BARRIL_DUREZA
            if "param/obj.prm" in orig:
                _, so, ao, oo = orig["param/obj.prm"]
                with open(iso, "rb") as g:
                    g.seek(dat_off + oo)
                    obj_prm = bytearray(g.read(so))
                if len(obj_prm) >= (OBJ_BARRIL + 1) * 0x80 and obj_prm[OBJ_BARRIL * 0x80] == 21:
                    struct.pack_into("<H", obj_prm, OBJ_BARRIL * 0x80 + 2, BARRIL_DUREZA)
                    f.seek(dat_off + oo)
                    f.write(obj_prm)
                    if done == 0:
                        log.append(f"Barriles: se rompen con {BARRIL_DUREZA} de daño de un golpe (antes 181)")
            # daño de los enemigos cuerpo a cuerpo (param/chr.prm), siempre desde el original y en su sitio
            if "param/chr.prm" in orig and (DANO_MAX_GOLPE or pulpo):
                _, sc, ac, oc = orig["param/chr.prm"]
                with open(iso, "rb") as g:
                    g.seek(dat_off + oc)
                    chr_orig = g.read(sc)
                chr_nuevo, n_bajados = rebajar_dano(chr_orig) if DANO_MAX_GOLPE else (chr_orig, 0)
                if pulpo:
                    chr_nuevo = bytearray(chr_nuevo)
                    r0 = kf4_pulpo.REGISTRO_PULPO * 0x450
                    if lang in destinos_pulpo:
                        chr_nuevo[r0:r0 + 0x450] = pulpo[1]
                    else:          # sin sitio para su modelo: el registro 48 es la serpiente (13)
                        chr_nuevo[r0:r0 + 0x450] = chr_nuevo[13 * 0x450:14 * 0x450]
                    chr_nuevo = bytes(chr_nuevo)
                f.seek(dat_off + oc)
                f.write(chr_nuevo)
                if done == 0 and DANO_MAX_GOLPE:
                    log.append(f"Serpiente: {n_bajados} golpes cuerpo a cuerpo rebajados a unos {DANO_MAX_GOLPE} de daño "
                               f"(con 50 de vida y sin armadura); los demás enemigos, como en el juego")
        done += 1
        # la página del arma con la fila de experiencia (siempre a partir del archivo original)
        _, d_a = _leer_dat(iso, lang, "menu/equip_a_para.dat")
        _, d_o = _leer_dat(iso, lang, "menu/option_para.dat")
        ent = tab.get("menu/equip_a_para.dat") or tab.get("menu\\equip_a_para.dat")
        if ent and d_a and d_o:
            nuevo_para = para_arma_con_exp(d_a, d_o) if exp_menu else d_a
            if nuevo_para is None:
                log.append(f"AVISO {lang}: equip_a_para.dat no es el que conozco; sin fila de experiencia")
            elif len(nuevo_para) > ent[2]:
                log.append(f"AVISO {lang}: la página del arma no cabe en su sitio del DAT ({len(nuevo_para)} > {ent[2]})")
            else:
                with open(out, "r+b") as f:
                    f.seek(dat_off + ent[3])
                    f.write(nuevo_para + bytes(ent[2] - len(nuevo_para)))
                    f.seek(ent[0] + 0x34)
                    f.write(struct.pack("<I", len(nuevo_para)))
    log.append(f"099.map escrito en {done} idiomas")
    return out, done


def generar_mapa(src, v, rumbo, log, d099=None, d031=None, cruz=True):
    """Monta el 099.map nuevo de una zona ya construida (v.construir() y fijar_offset(v) hechos)."""
    d099 = d099 if d099 is not None else src.read("099.map")
    d031 = d031 if d031 is not None else src.read("031.map")
    nam = src.read("param/item_nam.prm")
    item_modelo = {i: struct.unpack_from("<H", nam, i * 64 + 0x30)[0] for i in range(len(nam) // 64)}
    quiero = {item_modelo[i] for i, _ in v.objetos if item_modelo.get(i)}
    modelos = modelos_de_items(src, quiero, log)
    obp = src.read("param/obj.prm")
    obj_kind = {i: obp[i * 0x80] for i in range(len(obp) // 0x80)}
    import kf4_cruz

    def leer(nombre):
        try:
            return src.read(nombre) if src.has(nombre) else None
        except Exception:
            return None
    bloque = kf4_cruz.construir_bloque(leer, log)        # también lleva las cifras de la vida
    tipos = [t for t, _ in getattr(v, "enemigos", [])]
    # tamaño del archivo de cada bicho: si pasa de 512 KB (un bloque de pool) el juego se cuelga al cargarlo
    # (EntityPool_CopyLoadedFile, kfiv-decomp)
    v._tam_chr = {}
    try:
        prm = src.read("param/chr.prm")
        for t in set(tipos):
            r = int(t[4:]) if str(t).startswith("chr:") else {k: x[1] for k, x in ENEMIGOS.items()}.get(t)
            if r is None:
                continue
            modelo = struct.unpack_from("<H", prm, r * 0x450)[0]
            dos = struct.unpack_from("<H", prm, r * 0x450 + 0x10)[0] & 0x8000
            nombre = f"chr/c{modelo:04d}.chr"
            tam = src.names.get(nombre)
            n = tam[1] if isinstance(tam, tuple) else (os.path.getsize(tam) if tam else None)
            v._tam_chr[t] = (f"{nombre} {n // 1024 if n else '?'} KB" + (" (dos bloques)" if dos else "")
                             + (" AVISO: más grande que un bloque de pool" if n and n > (0x100000 if dos else 0x80000)
                                else ""))
    except Exception as e:
        log.append(f"(no pude mirar los archivos de los bichos: {e})")
    plantillas_obj = plantillas_objetos(src, log) if getattr(v, "kf_objetos", None) and "objetos" not in QUITAR \
        else None
    if "tipos" in QUITAR:          # prueba: todos los enemigos como el escarabajo de 099 (el que siempre ha ido)
        v.enemigos = [("escarabajo", p) for _, p in v.enemigos]
        tipos = ["escarabajo"]
    for t in list(QUITAR):         # prueba: --quitar solo58 / solo24 ... deja solo ese registro
        if t.startswith("solo"):
            v.enemigos = [(x, p) for x, p in v.enemigos if x == "chr:" + t[4:]]
    for t in list(QUITAR):         # prueba: --quitar junto11 / junto10: uno solo de ese registro a 3 m del inicio
        if t.startswith("junto"):
            x0, y0, z0 = v.inicio
            tipo = "escarabajo" if t[5:] == "11" else "chr:" + t[5:]
            v.enemigos = [(tipo, (x0 + 3.0, y0, z0 + (2.5 if t[5:] == "10" else 0.0)))]
            tipos = [tipo]
    if "pocos" in QUITAR:          # prueba: solo 8 enemigos
        v.enemigos = v.enemigos[:8]
    if "enemigos" in QUITAR:
        v.enemigos = []
        log.append("PRUEBA: sin enemigos")
    if QUITAR:
        log.append(f"PRUEBA: quitado {', '.join(sorted(QUITAR))}")
    return assemble(v, d099, d031, rumbo, log, plantillas_enemigos(src, log, tipos), item_modelo, modelos, obj_kind,
                    bloque, plantillas_obj)


# Lo que puede ocupar el mapa: el juego reserva 0xA80000 bytes para los archivos de mapa (core/memory.c). Al
# entrar en una partida el mapa se carga con MapChange (map_change.c), que vacía antes los dos huecos y no mira
# tamaños; solo la precarga de un mapa vecino (MapLoad_OpenFile) exige que quepan los dos, y este mapa no tiene
# vecinos. Se deja un margen de 64 KB.
MAPA_MAXIMO = 0xA80000 - 0x10000


def hueco_mapa(iso, lang="SPA"):
    """Bytes que puede ocupar el 099.map: si no cabe en su sitio del .DAT va al final de la ISO."""
    return MAPA_MAXIMO


def preparar_pulpo(src, v, log):
    """(chr, registro de chr.prm) del pulpo si el mapa lo lleva; si no se puede hacer, sus enemigos pasan a ser
    la serpiente (como antes)."""
    tipo = f"chr:{kf4_pulpo.REGISTRO_PULPO}"
    enemigos = getattr(v, "enemigos", [])
    if not any(t == tipo for t, _ in enemigos):
        return None
    if "pulpo" in QUITAR:              # prueba: sin el pulpo (serpientes como antes)
        v.enemigos = [("chr:13" if t == tipo else t, p) for t, p in enemigos]
        log.append("PRUEBA: sin el pulpo (van serpientes en su lugar)")
        return None
    try:
        import kf4_chr
        if getattr(v, "kf_mo", None) is None:
            raise RuntimeError("no tengo el MO.T del King's Field (los modelos de los bichos)")
        flor = kf4_chr.Chr(src.read(f"chr/c{kf4_pulpo.REGISTRO_BASE:04d}.chr"))
        datos, esq = kf4_pulpo.pulpo_chr(flor, v.kf_mo, v.kf_vram)
        if len(datos) > 0x80000:
            raise RuntimeError(f"el modelo ocupa {len(datos)} bytes, más que un bloque de pool")
        prm = src.read("param/chr.prm")
        b = kf4_pulpo.REGISTRO_BASE * 0x450
        reg = kf4_pulpo.pulpo_prm(prm[b:b + 0x450])
        n = sum(1 for t, _ in enemigos if t == tipo)
        log.append(f"Pulpo (Kraken del King's Field): {n} con su modelo, {esq.n} huesos y {len(kf4_pulpo.ORDEN_MOV)} movimientos "
                   f"({len(datos) // 1024} KB); se porta como la Flor oscura del IV y además da latigazos")
        return datos, reg
    except Exception as e:
        v.enemigos = [("chr:13" if t == tipo else t, p) for t, p in enemigos]
        log.append(f"AVISO: no pude hacer el pulpo ({e}); va la serpiente en su lugar")
        return None


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    semilla = 1
    rumbo = 0.0
    giro = 2.2
    mando = "dos_sticks"
    zona = "prologo"
    mapa_json = "mapa_torre.json"
    debug_ini = None
    for i, a in enumerate(sys.argv):
        if a == "--semilla" and i + 1 < len(sys.argv):
            semilla = int(sys.argv[i + 1])
            args = [x for x in args if x != sys.argv[i + 1]]
        if a == "--rumbo" and i + 1 < len(sys.argv):
            rumbo = float(sys.argv[i + 1])
            args = [x for x in args if x != sys.argv[i + 1]]
        if a == "--mapa" and i + 1 < len(sys.argv):
            mapa_json = sys.argv[i + 1]
            args = [x for x in args if x != sys.argv[i + 1]]
        if a == "--zona" and i + 1 < len(sys.argv):
            zona = sys.argv[i + 1].lower()
            args = [x for x in args if x != sys.argv[i + 1]]
        if a == "--mando" and i + 1 < len(sys.argv):
            mando = sys.argv[i + 1].lower()
            args = [x for x in args if x != sys.argv[i + 1]]
        if a == "--giro" and i + 1 < len(sys.argv):
            giro = float(sys.argv[i + 1].replace(",", "."))
            args = [x for x in args if x != sys.argv[i + 1]]
        if a == "--debug" and i + 1 < len(sys.argv) and sys.argv[i + 1].isdigit():
            debug_ini = sys.argv[i + 1].zfill(4)
            args = [x for x in args if x != sys.argv[i + 1]]
    if "--debug" in sys.argv and not debug_ini:
        debug_ini = "9999"
    solo = "--solo-mapa" in sys.argv
    if "--recortar" in sys.argv:
        global RECORTAR_TABLAS
        RECORTAR_TABLAS = True
    vida_numero = "--sin-vida-numero" not in sys.argv
    cruz = "--sin-cruz" not in sys.argv
    exp_menu = "--sin-exp" not in sys.argv
    global RELLENO
    for i, a in enumerate(sys.argv):
        if a == "--relleno" and i + 1 < len(sys.argv):
            RELLENO = int(float(sys.argv[i + 1]) * 1024 * 1024)
            args = [x for x in args if x != sys.argv[i + 1]]
    for i, a in enumerate(sys.argv):     # pruebas: --quitar agua,cielo,enemigos,objetos
        if a == "--quitar" and i + 1 < len(sys.argv):
            QUITAR.update(x.strip().lower() for x in sys.argv[i + 1].split(",") if x.strip())
            args = [x for x in args if x != sys.argv[i + 1]]
    import kf_malla
    if "agua" in QUITAR:
        kf_malla.AGUA_ANIMADA = False
    if "luz" in QUITAR:
        kf_malla.LUZ_SUAVE = False
        kf_malla.LUZ_INTERIOR = False
    if "fusion" in QUITAR:            # prueba: la colisión sin juntar (como antes)
        global FUSIONAR_COLISION
        FUSIONAR_COLISION = False
    if "texturas" in QUITAR:
        kf_malla.ESCRITURA_PARCIAL = False
    if args:
        src_path = os.path.abspath(args[0])
    else:
        # la ISO: en esta carpeta o en la de encima (FIELDIV-ENGINE: el .exe y la ISO fuera, las herramientas en engine)
        src_path = here
        for carpeta in (here, os.path.dirname(here)):
            isos = [f for f in os.listdir(carpeta) if f.lower().endswith(".iso") and "(valle)" not in f
                    and "(parche)" not in f]
            isos.sort(key=lambda f: ("(" in f, len(f), f))   # la ISO limpia primero, no las (debug)
            if isos:
                src_path = os.path.join(carpeta, isos[0])
                break
    src = md.Source(src_path)
    d099 = src.read("099.map")
    d031 = src.read("031.map")
    outdir = os.path.join(here, "kf4_valle")
    os.makedirs(outdir, exist_ok=True)
    log = [f"Semilla {semilla}"]
    print(f"Generando la zona {zona} (semilla {semilla})...")
    if zona == "valle":
        v = Valle(semilla)
    elif zona == "editor":
        import kf4_editor
        ruta = mapa_json if os.path.isabs(mapa_json) else os.path.join(here, mapa_json)
        if not os.path.isfile(ruta):
            raise SystemExit(f"No encuentro {ruta}: expórtalo desde el editor y ponlo en esta carpeta")
        v = kf4_editor.MapaEditor(semilla, ruta)
        log.append(f"Mapa del editor: {os.path.basename(ruta)}")
    else:
        import kf4_prologo
        v = kf4_prologo.Prologo(semilla)
    log.append(f"Zona: {zona}")
    v.construir()
    revisar(v.geo, log)
    log.append(f"Trozos extra para que no desaparezcan triángulos cerca de la cámara: {v.geo.trozos}")
    fijar_offset(v)
    log.append(f"Zona colocada en las coordenadas del Palacio de Oath (desplazamiento {OFFSET[0]:.0f}, {OFFSET[1]:.0f}, {OFFSET[2]:.0f})")
    log.append(f"Ventanas: {len(v.ventanas)}  puertas: {len(v.puertas)}  enemigos pedidos: "
               f"{len(getattr(v, 'enemigos', []))}")
    pulpo = preparar_pulpo(src, v, log)
    new_map, stats = generar_mapa(src, v, rumbo, log, d099, d031, cruz)
    if zona == "editor" and getattr(v, "kf_atlas", None) is not None:
        # si no cabe en la memoria de mapas se repite: primero quitando las caras que la roca tapa entera, luego
        # fundiendo a negro (y quitando) antes lo que queda bajo el agua
        import kf_malla
        pasos = [("parte del decorado (solo barriles, mesas, sillas, la fuente...)",
                  lambda: setattr(kf_malla, "PROPS_NIVEL", 1)),
                 ("el decorado (menos la fuente)", lambda: setattr(kf_malla, "PROPS_NIVEL", 0)),
                 ("lo hondo bajo el agua (negro desde 1,5 m)", lambda: setattr(kf_malla, "FUNDIDO_AGUA", 1.5)),
                 ("caras tapadas por la roca", lambda: setattr(kf_malla, "QUITAR_OCULTAS", True)),
                 ("toda cara que mira a roca (puede faltar alguna en lo alto de los riscos)",
                  lambda: setattr(kf_malla, "OCULTAS_ESTRICTO", True))]
        for nombre, aplicar in pasos:
            if len(new_map) <= MAPA_MAXIMO:
                break
            aplicar()
            log.append(f"El mapa no cabía ({len(new_map)} bytes): se repite quitando {nombre}")
            v = kf4_editor.MapaEditor(semilla, ruta)
            v.construir()
            fijar_offset(v)
            pulpo = preparar_pulpo(src, v, [])
            new_map, stats = generar_mapa(src, v, rumbo, log, d099, d031, cruz)
    with open(os.path.join(outdir, "099.map"), "wb") as o:
        o.write(new_map)
    if not solo and src.kind == "ISO":
        iso_out, n = patch_iso(src_path, new_map, log, debug_ini, giro, mando, vida_numero, cruz, exp_menu, pulpo)
        log.append(f"ISO -> {iso_out}")
        with open(os.path.join(outdir, "iso_lista.txt"), "w", encoding="utf-8") as o:
            o.write(iso_out)
    with open(os.path.join(outdir, "resumen.txt"), "w", encoding="utf-8") as o:
        o.write("\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main()
