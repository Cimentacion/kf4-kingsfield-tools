#!/usr/bin/env python3
"""
kf_malla.py - La geometría real de un mapa de King's Field de PS1 (el europeo / KF2 japonés, o King's Field II
USA / KF3 japonés) dentro del generador de mapas de King's Field IV.

En el PS1 cada casilla de la rejilla de 80 x 80 pone uno de los ~200 modelos del nivel (RTMD.T) a su altura y con
su giro (en el europeo, dos capas por casilla). Aquí se pone cada modelo tal cual, con:
  - la luz horneada del 4 por vértice (y los colores de vértice del mapa: sombra al pie de las paredes, tinte)
  - sus texturas: las regiones de textura que usa el nivel van a un atlas en los huecos de textura del 099.map,
    cada región con su propia paleta de 16 colores (las paletas van en un hueco reservado para ellas)
  - colisión: las caras que miran arriba son suelo, las verticales pared
  - se quitan las caras que nunca se ven (pegadas a la de otra casilla, del revés)

Formatos: FORMATS.md de github.com/AnatoliySolomichev/kings_field_2_re y KFModTool de github.com/IvanDSM/KingsFieldRE.
"""

import collections
import math

import numpy as np

import kf2_tex

ESCALA = 2.5 / 2048          # metros por unidad del PS1 (una casilla = 2048 = 2,5 m)
ALTURA_M = 128 / 2048 * 2.5  # metros por unidad de altura de la rejilla
N_KF = 80

# huecos de textura del editor (todos PSMT4) que se usan para el atlas, y el que guarda las paletas
HUECOS_ATLAS = ["losas", "muro", "roca_gris", "musgo", "grava", "ladrillo", "sillar", "roca", "nicho",
                "piedra_lisa", "banda", "madera", "friso"]
HUECO_PALETAS = "estrias"     # 256 x 256 de 4 bits = 128 bloques de la memoria de vídeo: 128 paletas
CELDA_ATLAS = 64
ULTIMAS_OCULTAS = 0
# formato de esos huecos en el 099.map de SLES_509.20 (TBW, ancho, alto); se comprueba al montar el mapa
FORMATO_HUECOS = {"losas": (4, 256, 256), "sillar": (2, 128, 128), "muro": (4, 256, 256), "roca": (2, 128, 128),
                  "roca_gris": (4, 256, 256), "musgo": (4, 256, 256), "grava": (4, 256, 256),
                  "piedra_lisa": (4, 256, 128), "ladrillo": (4, 256, 256), "banda": (4, 256, 128),
                  "estrias": (4, 256, 256), "madera": (4, 256, 128), "friso": (4, 256, 128), "nicho": (2, 128, 128)}


def campos_huecos(huecos_tex):
    """{(tbp, cbp): campos} como los de kf4_tex.tex0_fields, para los huecos del editor."""
    out = {}
    for nombre, (tbw, w, h) in FORMATO_HUECOS.items():
        tbp, cbp = huecos_tex[nombre]
        out[(tbp, cbp)] = {"TBP": tbp, "CBP": cbp, "TBW": tbw, "W": w, "H": h, "PSM": 0x14}
    return out


def _girar(v, rot):
    """Un cuarto de vuelta en el eje Y del PlayStation: (x, y, z) -> (z, y, -x), rot veces."""
    x, y, z = v
    for _ in range(rot & 3):
        x, y, z = z, y, -x
    return x, y, z


class Datos:
    """Lo que hace falta de un nivel: modelos de casilla, la rejilla y la memoria de vídeo."""

    def __init__(self, arch, juego, nivel):
        import kf2_a_editor as ka
        self.juego, self.nivel = juego, nivel
        self.objs = kf2_tex.objetos_tmd(arch["RTMD.T"][nivel])
        e = arch["FDAT.T"][3 * nivel]
        self.grid = np.frombuffer(e[4:4 + 64000], np.uint8).reshape(N_KF, N_KF, 10)
        self.vram = kf2_tex.vram_nivel(arch["FDAT.T"], arch["RTIM.T"], nivel, ka.BASE_VRAM[juego])
        # qué casillas tienen suelo (se puede estar) y cuáles son roca (no hay suelo y sí paredes o nada)
        tipos = ka._tipos_casilla(self.objs)
        self.suelo, self.roca = set(), set()
        for z in range(N_KF):
            for x in range(N_KF):
                c = self.grid[z, x]
                capas = [int(c[5]), int(c[0])] if juego == "kf1" else [int(c[5])]
                validas = [t for t in capas if t < len(tipos)]
                if juego == "kf3":
                    andable = c[8] != 255
                else:
                    andable = any(tipos[t][0] for t in validas)
                if andable:
                    self.suelo.add((x, z))
                elif not validas or any(tipos[t][2] for t in validas):
                    self.roca.add((x, z))
        # capas: (modelo, altura, giro) de cada casilla; KF3 solo usa la segunda (la primera siempre vacía)
        self.capas = []
        for z in range(N_KF):
            for x in range(N_KF):
                c = self.grid[z, x]
                for b in ((0, 5) if juego == "kf1" else (5,)):
                    t = int(c[b])
                    if t < len(self.objs) and self.objs[t][1]:
                        self.capas.append((x, z, t, int(c[b + 1]), int(c[b + 2]) & 3))
        # lo más alto de los modelos de cada casilla (m, en la altura del editor sin h0): para saber si una roca
        # tapa de verdad la cara que la mira
        self.topes_crudos = {}
        self.fondos_crudos = {}       # lo más bajo de los modelos de cada casilla (el fondo del mar)
        for (x, z, t, elev, rot) in self.capas:
            verts = self.objs[t][0]
            if not verts:
                continue
            alto = elev * ALTURA_M + max(-v[1] for v in verts) * ESCALA
            self.topes_crudos[(x, z)] = max(self.topes_crudos.get((x, z), -1e9), alto)
            bajo = elev * ALTURA_M + min(-v[1] for v in verts) * ESCALA
            self.fondos_crudos[(x, z)] = min(self.fondos_crudos.get((x, z), 1e9), bajo)
        self.topes = {}
        if juego == "kf1":       # los agujeros (pozos, huecos con agua) no son roca: kf2_a_editor.rejilla_kf1
            celdas = ka.rejilla_kf1(arch["FDAT.T"], arch["RTMD.T"], nivel)
            andables = {k for k, c in celdas.items() if c["forma"] != 255}   # incluye agua somera, escaleras, rellanos
            self.roca -= {k for k, c in celdas.items() if c.get("hoyo")} | andables
            self.suelo |= andables
            # escaleras: en la colisión van como rampa lisa (una cara inclinada por casilla), no peldaño a peldaño.
            # Con peldaños de 31 cm el 4 entra en "subiendo" en cada uno (solo sube de golpe 16,7 cm) y deja de
            # mirar el suelo; corriendo se adelanta a la subida y se cuela entre peldaños. En una rampa lisa sube
            # lo que avanza en cada fotograma (12 cm andando o corriendo normal) y nunca entra en ese modo.
            self.rampas = {k: (c["rampa"], c["h"]) for k, c in celdas.items() if c.get("rampa")}
            self.planos = {k: (c["plano"], c["h"]) for k, c in celdas.items() if c.get("plano")}
        else:
            self.rampas, self.planos = {}, {}
        # objetos de decorado del nivel original (barriles, mesas, tumbas, la fuente...): su modelo de MO.T
        # (entrada 128 + id del objeto) se pone tal cual en el mapa, como las casillas
        self.props = []
        self.fuentes = []          # (columna, fila, fino x, fino z) de las fuentes que curan (195, WaterWell)
        # casillas de puerta o pared secreta sin modelo de suelo (el hueco de la pared): se les pone suelo
        self.huecos_puerta = set()
        self.puertas_kf = []       # (columna, fila, id) de las puertas: su modelo de MO.T da la textura de la puerta
        self.mo = arch.get("MO.T")
        if juego == "kf1":
            import kf1_objetos
            _, objetos_ = kf1_objetos.leer(arch["FDAT.T"], nivel)
            for o in objetos_:
                if o["id"] in kf1_objetos.PUERTAS:
                    self.puertas_kf.append((o["y"], o["x"], o["id"]))
                if o["id"] in kf1_objetos.PUERTAS:
                    # (las paredes secretas no: su modelo de MO.T trae el suelo y el techo de alrededor)
                    col, fila = o["y"], o["x"]
                    c = self.grid[fila, col]
                    if not any(int(c[b]) < len(self.objs) and self.objs[int(c[b])][1] for b in (0, 5)):
                        self.huecos_puerta.add((col, fila))
        if juego == "kf1" and arch.get("MO.T"):
            todos = props_kf1(arch, nivel, self.grid)
            self.fuentes = [(p[0], p[1], p[6], p[7]) for p in todos if p[2] == FUENTE_ID]
            dejar = None if PROPS_NIVEL >= 2 else (PROPS_LIGEROS if PROPS_NIVEL == 1 else {FUENTE_ID})
            self.props = [p for p in todos if dejar is None or p[2] in dejar]
        # las paredes secretas del King's Field con su modelo de verdad (MO.T): lo fijo (suelo, techo, el nicho) va
        # en el mapa como una casilla más; la pared que sube (caras verticales de 130 y 205) va aparte, al objeto
        self.secretas = []
        if juego == "kf1" and arch.get("MO.T"):
            import kf1_objetos
            self.secretas = props_kf1(arch, nivel, self.grid, ids=kf1_objetos.SECRETAS)


# objetos de decorado: los que no son de coger (< 120), cofres, puertas, paredes secretas, cielos/luna, zonas de
# carga, el invisible ni trampas que se mueven (ObjectID de KFModTool, kf2/object.h)
FUENTE_ID = 195
NICHOS_KF = {131, 138, 209, 214}          # paredes con nicho (kf1_objetos.NICHOS): fijas, no suben
# cuánto decorado: 2 todo (menos lo muy pesado), 1 solo lo ligero, 0 solo la fuente (si el mapa no cabe, kf4_valle
# lo va bajando antes de quitar caras)
PROPS_NIVEL = 2
LUZ_FUENTE_RADIO = 14.0                    # m alrededor de la fuente que cura con la luz azulada (toda su sala)
LUZ_FUENTE_TINTE = (1.25, 1.55, 2.3)       # r, g, b: multiplica el color (la sala tenía ~50 de 255: muy oscura)
LUZ_FUENTE_SUMA = (10.0, 26.0, 55.0)       # y se le suma esto: luz azul aunque la pared sea casi negra
# antorchas, farolas y velas del nivel original: una luz cálida suave alrededor (colores de vértice)
LUCES_ID = {163, 277, 279, 280}            # farola del mago, linterna, antorcha de pared y de techo
LUZ_CALIDA_RADIO = 6.0
LUZ_CALIDA_SUMA = (60.0, 38.0, 14.0)       # lo que suma en el centro (se funde hasta el radio)
PROPS_LIGEROS = {195, 179, 180, 136, 256, 259, 230, 159, 160, 161}
# (los huesos, 143 y 144, son de 400 a 700 triángulos cada uno y hay docenas: no caben)
# (también los indicadores 189, el soldado muerto 141 y la espada rota 264: 280-700 cada uno)
# (los barriles, 179, van como el barril del 4 que se rompe: kf1_objetos)
NO_PROPS = set(range(0, 136)) | set(range(240, 250)) | {141, 143, 144, 179, 183, 189, 264, 194, 200, 201, 202, 203, 204, 205, 206, 209, 213, 214,
                                                        224, 231}


def props_kf1(arch, nivel, grid, ids=None):
    """[(columna, fila, id, verts, prims, altura de rejilla, fino x, fino z, giro rad, fz)] de los objetos de
    decorado del nivel con modelo en MO.T."""
    import kf1_objetos
    import struct
    _, objetos = kf1_objetos.leer(arch["FDAT.T"], nivel)
    mo = arch["MO.T"]
    cache = {}
    out = []
    for o in objetos:
        oid = o["id"]
        if (oid not in ids if ids is not None else oid in NO_PROPS) or 128 + oid >= len(mo):
            continue
        if oid not in cache:
            d = mo[128 + oid]
            modelo = None
            if d and len(d) > 16:
                tmd = struct.unpack_from("<I", d, 8)[0]
                if tmd < len(d) - 12 and d[tmd] == 0x41:
                    try:
                        ob = kf2_tex.objetos_tmd(d[tmd:], por_8=False)
                        if ob and ob[0][0] and ob[0][1]:
                            modelo = ob[0]
                    except (ValueError, struct.error):
                        modelo = None
            cache[oid] = modelo
        if cache[oid] is None:
            continue
        col, fila = o["y"], o["x"]
        c = grid[fila, col]
        elev = int(c[6]) if o["capa"] == 0 else int(c[1])      # capa 0 = bytes 5-7 de la casilla
        if (c[5] if o["capa"] == 0 else c[0]) == 255:
            elev = int(c[6]) if c[5] != 255 else int(c[1])
        verts, prims = cache[oid]
        out.append((col, fila, oid, verts, prims, elev, kf1_objetos._fino(o["fx"]), kf1_objetos._fino(o["fy"]),
                    o["giro"] / 4096.0 * 2 * math.pi, o["fz"]))
    return out


def _piezas(datos, editor, pad, h0):
    """Lo que se pone: cada modelo de casilla y cada objeto de decorado, con sus vértices ya en el mundo.
    (x, z, prims, mundo, girar_normal, rot)"""
    C = editor.celda
    _SECRETA_ACTUAL[0] = None
    for (x, z, t, elev, rot) in datos.capas:
        verts, prims = datos.objs[t]
        ox = editor.ox + (x + pad + 0.5) * C
        oy = editor.oy + (z + pad + 0.5) * C
        oz = (elev - h0) * ALTURA_M
        mundo = []
        for v in verts:
            gx, gy, gz = _girar(v, rot)
            mundo.append((ox + gx * ESCALA, oy + gz * ESCALA, oz - gy * ESCALA))
        yield x, z, prims, mundo, (lambda n, r=rot: _girar(n, r)), rot
    for (x, z, oid, verts, prims, elev, ffx, ffz, ang, fz) in datos.props:
        # la posición fina: "fy" va a lo largo de las columnas y "fx" de las filas (kf1_objetos.para_editor)
        ox = editor.ox + (x + pad + ffz) * C
        oy = editor.oy + (z + pad + ffx) * C
        oz = (elev - h0) * ALTURA_M - fz * ESCALA
        ca, sa = math.cos(ang), math.sin(ang)

        def gira(v, ca=ca, sa=sa):            # como _girar, pero cualquier ángulo (1024 = un cuarto de vuelta)
            x_, y_, z_ = v
            return x_ * ca + z_ * sa, y_, -x_ * sa + z_ * ca
        mundo = []
        for v in verts:
            gx, gy, gz = gira(v)
            mundo.append((ox + gx * ESCALA, oy + gz * ESCALA, oz - gy * ESCALA))
        yield x, z, prims, mundo, gira, -1 - oid    # < 0: objeto (pequeño: sus triángulos no se trocean)
    for (x, z, oid, verts, prims, elev, ffx, ffz, ang, fz) in getattr(datos, "secretas", []):
        # la pared secreta: como una casilla (con colisión y troceada), en su posición fina y su giro
        ox = editor.ox + (x + pad + ffz) * C
        oy = editor.oy + (z + pad + ffx) * C
        oz = (elev - h0) * ALTURA_M - fz * ESCALA
        ca, sa = math.cos(ang), math.sin(ang)

        def gira(v, ca=ca, sa=sa):
            x_, y_, z_ = v
            return x_ * ca + z_ * sa, y_, -x_ * sa + z_ * ca
        mundo = []
        for v in verts:
            gx, gy, gz = gira(v)
            mundo.append((ox + gx * ESCALA, oy + gz * ESCALA, oz - gy * ESCALA))
        _SECRETA_ACTUAL[0] = (oid, (ox, oy, oz))
        yield x, z, prims, mundo, gira, int(round(ang / (math.pi / 2))) & 3
    _SECRETA_ACTUAL[0] = None


_SECRETA_ACTUAL = [None]   # (id, posición) de la pared secreta que está dando _piezas (para sacar la que sube)


# agua animada: el 4 compone cada fotograma una textura de 32 bits con capas que se desplazan (tabla de texturas
# animadas de la cabecera, como el agua de 000); aquí: fuente PSMT8 128x128 con el agua del King's Field en
# mosaico, su paleta, y el destino que dibujan los polígonos de agua. Van en 0x3140..0x3290, una zona de las
# texturas de 099 que no usa ningún hueco del editor ni el atlas.
LUZ_SUAVE = True        # False: la sombra de techo por casilla, como antes (--quitar luz)
ESCRITURA_PARCIAL = True   # False: se reescriben las subidas enteras, como antes (--quitar texturas)
AGUA_ANIMADA = True     # False: el agua va al atlas como lo demás (kf4_valle --quitar agua)
AGUA_DST = 0x3140       # PSMCT32 128x128, TBW 2 (0x100 bloques)
AGUA_SRC = 0x3240       # PSMT8 128x128, TBW 2 (0x40 bloques)
AGUA_CLUT = 0x3280      # paleta de 256 (CSM1, 4 bloques)
PUNTOS_TROZO = 600      # puntos de colisión por registro antes de partir el trozo (el 4 admite 1008)
ESCALON_KF = 1.35       # m: una pared de modelo que no sube más que esto sobre el suelo no va en la colisión
PAREDES_REALES = True   # las paredes de los modelos también en la colisión (no solo las de la rejilla)
OCULTAS_ESTRICTO = False  # (solo si el mapa no cabe) toda cara que mira a roca se quita
QUITAR_OCULTAS = False  # quitar las caras que miran a roca: solo ahorraba un 3 % y se comía caras que sí se ven
OSCURO_AGUA = 0.5       # el agua: su color de vértice por esto (más oscura)
FUNDIDO_AGUA = 3.0      # m bajo el nivel del agua en los que las paredes pasan a negro
JUNTAR_MAR = True       # el mar abierto y el fondo negro de 2 x 2 casillas (_juntar_mar)
TROZO_AGUA = 40         # casillas por registro de agua (pocos registros: el agua va aparte, transparente)


def es_agua(datos, region):
    """Las regiones de agua del King's Field: en las páginas de abajo de la VRAM (las que el PS1 anima) y
    azuladas. Se guarda la respuesta por región."""
    cache = datos.__dict__.setdefault("_agua", {})
    if region not in cache:
        tpage = region[0]
        ok = False
        if tpage & 0x10:
            idx, pal = _region_indices(datos.vram, *region)
            m = pal[idx][..., :3].reshape(-1, 3).mean(0)
            ok = m[2] - m[0] > 15 and m[2] >= m[1]
        cache[region] = ok
    return cache[region]


def _region(uvs):
    """El cuadro alineado de 64 (o 128) téxeles de la página que usa un polígono, como en kf2_tex."""
    us, vs = [u for u, _ in uvs], [v for _, v in uvs]
    lado = 64 if max(max(us) - min(us), max(vs) - min(vs)) <= 64 else 128
    cu, cv = (min(us) + max(us)) // 2 // lado * lado, (min(vs) + max(vs)) // 2 // lado * lado
    return cu, cv, lado


class Atlas:
    """Reparte las regiones de textura del nivel en los huecos y les da paleta propia."""

    def __init__(self, huecos_tex, fs):
        """huecos_tex: {nombre: (tbp, cbp)} (kf4_editor.TEXTURAS); fs: {(tbp, cbp): campos TEX0 de esa textura}."""
        self.huecos = []
        for nombre in HUECOS_ATLAS:
            clave = huecos_tex[nombre]
            f = fs.get(clave)
            if f is None or f["PSM"] != 0x14:
                continue
            libres = [(x, y) for y in range(0, f["H"], CELDA_ATLAS) for x in range(0, f["W"], CELDA_ATLAS)]
            self.huecos.append({"nombre": nombre, "clave": clave, "f": f, "libres": libres,
                                "img": np.zeros((f["H"], f["W"]), np.uint8)})
        fp = fs.get(huecos_tex[HUECO_PALETAS])
        self.paletas_libres = [fp["TBP"] + k for k in range(fp["W"] * fp["H"] // 2 // 256)] if fp else []
        self.clave_paletas = huecos_tex[HUECO_PALETAS]
        self.sitio = {}          # región -> (hueco, x, y, lado, cbp)
        self.agua_usos = collections.Counter()   # regiones de agua -> polígonos
        self.agua = None         # (índices 128x128, paleta 16 x RGBA) de la fuente del agua animada
        self.paletas = {}        # cbp -> paleta 16 x RGBA

    def poner(self, region, img, pal):
        """img: índices (lado x lado) de la región; pal: 16 x RGBA. Devuelve True si cupo."""
        if region in self.sitio:
            return True
        lado = img.shape[0]
        if not self.paletas_libres:
            return False
        for h in self.huecos:
            for (x, y) in list(h["libres"]):
                celdas = [(x + dx, y + dy) for dy in range(0, lado, CELDA_ATLAS) for dx in range(0, lado, CELDA_ATLAS)]
                if x + lado > h["f"]["W"] or y + lado > h["f"]["H"] or any(c not in h["libres"] for c in celdas):
                    continue
                for c in celdas:
                    h["libres"].remove(c)
                h["img"][y:y + lado, x:x + lado] = img
                cbp = self.paletas_libres.pop(0)
                self.paletas[cbp] = pal
                self.sitio[region] = (h, x, y, lado, cbp)
                return True
        return False


def _region_indices(vram, tpage, clut, cu, cv, lado):
    """La región como índices de 4 bits y su paleta (16 x RGBA, alfa 0x80 opaco) del PS1."""
    px0, py0 = (tpage & 0xF) * 64, ((tpage >> 4) & 1) * 256
    cx, cy = (clut & 0x3F) * 16, (clut >> 6) & 0x1FF
    pal16 = vram[cy, cx:cx + 16].astype(np.uint32)
    pal = np.zeros((16, 4), np.uint8)
    for k, c in enumerate([(pal16 & 31), (pal16 >> 5) & 31, (pal16 >> 10) & 31]):
        pal[:, k] = (c << 3) | (c >> 2)
    pal[:, 3] = 0x80
    vacio = pal16 == 0
    if vacio.any() and not vacio.all():        # el color 0 (transparente en el PS1): el medio de los demás
        pal[vacio, :3] = pal[~vacio, :3].mean(0).astype(np.uint8)
    hw = vram[py0:py0 + 256, px0:px0 + 64].astype(np.uint32)
    idx = np.stack([(hw >> (4 * k)) & 0xF for k in range(4)], axis=2).reshape(256, 256)
    return idx[cv:cv + lado, cu:cu + lado].astype(np.uint8), pal


def puntos_por_trozo(editor):
    """{trozo: puntos de colisión distintos} (como los cuenta build_csk)."""
    out = {}
    for ch, k in editor.geo.coll.items():
        pts = set()
        for kind in ("wall", "floor", "hazard"):
            for s_ in k.get(kind, []):
                for p in s_:
                    pts.add(tuple(round(v, 3) for v in p))
        out[ch] = len(pts)
    return out


FORZAR_PARTIR = {}      # trozo de 8 x 8 -> 4 o 2: lo que hay que partir porque no cupo (lo rellena kf4_editor)


def construir(editor, datos, h0, atlas, pad, colision=True):
    """Pone los modelos de las casillas en editor.geo. h0: la altura de rejilla que es el 0 del editor.
    Devuelve {clave de textura nueva: clave del hueco} para las plantillas de paquete."""
    C = editor.celda
    plantillas = {}
    regiones_sin_sitio = 0
    caras = collections.Counter()
    por_grupo = collections.defaultdict(list)
    cache_int = {}
    datos.topes = {k: v - h0 * ALTURA_M for k, v in datos.topes_crudos.items()}
    datos.fondos = {k: v - h0 * ALTURA_M for k, v in datos.fondos_crudos.items()}
    con_agua = set()          # casillas con caras de agua (también las de la orilla en diagonal)
    paredes_tile = collections.defaultdict(collections.Counter)   # casilla -> regiones de textura de sus paredes
    pisos = {}
    suelo_tex = {}            # casilla -> (clave, u0, v0, du, dv) de una cara de suelo suya (para los huecos)
    suelo_alt = {}
    paneles = {}              # posición de la puerta secreta -> [(textura, triángulo)] de la pared que sube
    suelos_secreta = set()    # casillas bajo el suelo de los modelos de pared secreta (se les pone suelo)
    con_suelo = set()         # casillas con alguna cara de suelo (mirando arriba)
    editor.kf_paneles = paneles
    cantos = []
    mar = {}
    negros = []
    # el nivel del agua (el más repetido entre las casillas de agua/vacío): por debajo, todo se funde a negro
    vac = [round(v, 2) for k, v in datos.topes.items() if k not in datos.suelo and k not in datos.roca]
    nivel_agua = collections.Counter(vac).most_common(1)[0][0] if vac else None
    clave_negra = None
    trozo_de = _trozos(editor, datos, pad, h0) if colision else \
        (lambda x, z: ("G", (x + pad) // editor.trozo, (z + pad) // editor.trozo))
    # índice de caras horizontales para quitar las que se tapan entre casillas (suelo bajo una tapa idéntica)
    for (x, z) in datos.suelo:
        pisos[(x, z)] = editor.altura(editor.ox + (x + pad + 0.5) * C, editor.oy + (z + pad + 0.5) * C)
    abiertas = {(x, z) for z in range(N_KF) for x in range(N_KF) if (x, z) not in datos.roca}
    cerca_abierta = {(x + dx, z + dz) for (x, z) in abiertas for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
    # cerca del agua (a 3 casillas o menos de una casilla con agua o vacía): solo ahí se funde a negro lo que queda
    # por debajo del nivel del mar; lo que está bajo ese nivel en otra parte (una sima, un sótano) se queda como es
    mojadas = {(x, z) for z in range(N_KF) for x in range(N_KF) if (x, z) not in datos.suelo and (x, z) not in datos.roca}
    cerca_agua = {(x + dx, z + dz) for (x, z) in mojadas for dx in range(-3, 4) for dz in range(-3, 4)}
    cerca_suelo = {(x + dx, z + dz) for (x, z) in datos.suelo for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
    # la sala de la fuente que cura: luz más clara y azulada alrededor (colores de vértice)
    luz_fuente = []
    for (col, fila, ffx, ffz) in getattr(datos, "fuentes", []):
        fxw = editor.ox + (col + pad + ffz) * C
        fyw = editor.oy + (fila + pad + ffx) * C
        luz_fuente.append((fxw, fyw, editor.altura(fxw, fyw)))

    calidas = []
    for (x_, z_, oid, verts, prims, elev, ffx, ffz, ang, fz) in getattr(datos, "props", []):
        if oid in LUCES_ID:
            calidas.append((editor.ox + (x_ + pad + ffz) * C, editor.oy + (z_ + pad + ffx) * C,
                            (elev - h0) * ALTURA_M - fz * ESCALA + 0.8))

    def azular(cols, P):
        if calidas:
            out = []
            for c, p in zip(cols, P):
                w = 0.0
                for (lx, ly, lz) in calidas:
                    d = math.sqrt((p[0] - lx) ** 2 + (p[1] - ly) ** 2 + (p[2] - lz) ** 2)
                    if d < LUZ_CALIDA_RADIO:
                        t = 1.0 - d / LUZ_CALIDA_RADIO
                        w += t * t
                if w > 0:
                    w = min(w, 1.5)
                    c = tuple(min(255.0, c[q] * (1.0 + 0.25 * w) + w * LUZ_CALIDA_SUMA[q]) for q in range(3)) + tuple(c[3:])
                out.append(c)
            cols = out
        if not luz_fuente:
            return cols
        out = []
        for c, p in zip(cols, P):
            w = 0.0
            for (fx_, fy_, fz_) in luz_fuente:
                d = math.hypot(p[0] - fx_, p[1] - fy_)
                if d < LUZ_FUENTE_RADIO and -2.0 < p[2] - fz_ < 9.0:
                    t = min(1.0, (1.0 - d / LUZ_FUENTE_RADIO) * 1.6)     # llena hasta media sala, luego se funde
                    w = max(w, t * t * (3 - 2 * t))
            if w > 0:
                c = tuple(min(255.0, c[q] * (1.0 + w * (LUZ_FUENTE_TINTE[q] - 1.0)) + w * LUZ_FUENTE_SUMA[q])
                          for q in range(3)) + tuple(c[3:])
            out.append(c)
        return out
    for (x, z, prims, mundo, girar_n, rot) in _piezas(datos, editor, pad, h0):
        for tpage, clut, uvs, refs, nrm_ps in prims:
            if tpage is None or (tpage >> 7) & 3:
                continue
            cu, cv, lado = _region(uvs)
            region = (tpage, clut, cu, cv, lado)
            agua = AGUA_ANIMADA and es_agua(datos, region)
            if agua:
                atlas.agua_usos[region] += 1
                con_agua.add((x, z))
            elif region not in atlas.sitio:
                img, pal = _region_indices(datos.vram, tpage, clut, cu, cv, lado)
                if not atlas.poner(region, img, pal):
                    regiones_sin_sitio += 1
                    continue
            if agua:
                # la textura animada: el cuadro de la región ocupa la mitad (en la fuente va en mosaico 2x2)
                base = atlas.huecos[0]["clave"] if atlas.huecos else None
                clave = (AGUA_DST, 0)
                if base:
                    plantillas[clave] = base
                ax = ay = 0
                W = H = 2 * lado
            else:
                h, ax, ay, lado, cbp = atlas.sitio[region]
                W, H = h["f"]["W"], h["f"]["H"]
                clave = (h["clave"][0], cbp)
                plantillas[clave] = h["clave"]
            P = [mundo[r] for r in refs]
            vista = _visible(P, nrm_ps, rot, editor, pad, datos) if QUITAR_OCULTAS and rot >= 0 else True
            if not vista:
                caras["ocultas"] += 1
                continue
            # normal: la del modelo (girada) si la hay; si no, la geométrica
            if nrm_ps is not None:
                nx, ny, nz = girar_n(nrm_ps)
                n = (nx / 4096.0, nz / 4096.0, -ny / 4096.0)
            else:
                a, b, c = P[0], P[1], P[2]
                n = _norm(_cross(_sub(b, a), _sub(c, a)))
            uv = [((ax + min(u - cu, lado)) / W, (ay + min(vv - cv, lado)) / H) for (u, vv) in uvs]
            sec = _SECRETA_ACTUAL[0]
            if sec and sec[0] not in NICHOS_KF and nrm_ps is not None and nrm_ps[1] == 0 and not agua:
                # la pared que sube de la puerta secreta: al objeto (kf4_valle), no al mapa ni a su colisión
                # la luz, la de un poco por delante de la cara: en la cara misma (el borde de la casilla) salía la
                # de la roca de al lado, casi negra
                fuera = [(p[0] + n[0] * 0.4, p[1] + n[1] * 0.4, p[2]) for p in P]
                cols = azular([editor.luzv(q, n, _interior(editor, q, cache_int)) for q in fuera], P)
                tex = (h["f"]["TBP"], cbp, h["f"]["TBW"], W, H, 0x14)
                cara = [(P[k], uv[k], cols[k], n) for k in range(len(P))]
                paneles.setdefault(sec[1], []).extend(
                    (tex, tuple(cara[k] for k in tri)) for tri in (((0, 1, 2), (1, 3, 2)) if len(P) == 4 else ((0, 1, 2),)))
                continue
            if rot >= 0 and not agua and n[2] > 0.7:
                con_suelo.add((x, z))
            if rot >= 0 and not agua and len(P) == 4 and n[2] > 0.7:
                # la cara horizontal más baja de la casilla: su suelo (la primera podía ser el techo, gris azulado)
                a_, b_, c_ = P[0], P[1], P[2]
                nn_ = _norm(_cross(_sub(b_, a_), _sub(c_, a_)))
                alt_ = sum(p_[2] for p_ in P) / 4.0
                if abs(nn_[2]) > 0.9 and ((x, z) not in suelo_tex or alt_ < suelo_alt[(x, z)]):
                    suelo_tex[(x, z)] = (clave, ax / W, ay / H, lado / W, lado / H)
                    suelo_alt[(x, z)] = alt_
            if LUZ_SUAVE:
                cols = [editor.luzv(p, n, _interior(editor, p, cache_int)) for p in P]
            else:
                ce = editor.celda_en(x + pad, z + pad)
                it = 0.55 if isinstance(ce, dict) and ce.get("techo") is not None else 0.0
                cols = [editor.luzv(p, n, it) for p in P]
            # el color pintado del mapa (manchas de tono y de luz, sombra al pie de las paredes: los colores de
            # vértice que pone kf2_a_editor) tiñe también los modelos de verdad, como a las piezas del editor
            if n[2] > 0.5:        # solo el suelo: en las paredes la sombra del pie las oscurecería enteras
                cols = [tuple(c[q] * m[q] for q in range(3))
                        for c, m in zip(cols, (editor.color_en(p[0], p[1]) for p in P))]
            cols = azular(cols, P)
            bajo_mar = nivel_agua is not None and (x, z) in cerca_agua
            if bajo_mar and not agua:
                # bajo el agua, degradado a negro (3 m): los riscos y el fondo se unen con el fondo negro
                cols = [tuple(q * min(1.0, max(0.0, 1.0 - (nivel_agua - p[2]) / FUNDIDO_AGUA)) for q in c)
                        if p[2] < nivel_agua else c for c, p in zip(cols, P)]
                if clave_negra is None:
                    clave_negra = (clave, ax / W, ay / H)
            if agua:
                # agua: alfa de vértice 0x40 (la mitad), como el agua del 4; va en registros propios (tardíos)
                cols = [(c[0] * OSCURO_AGUA, c[1] * OSCURO_AGUA, c[2] * OSCURO_AGUA, 0x40) for c in cols]
                ch = ("A", (x + pad) // TROZO_AGUA, (z + pad) // TROZO_AGUA)
                if JUNTAR_MAR and len(P) == 4 and (x, z) not in datos.suelo and (x, z) not in datos.roca \
                        and max(p[2] for p in P) - min(p[2] for p in P) < 0.01:
                    mar[(x, z)] = (P, cols, n, clave)      # el mar abierto: se junta de 2 en 2 casillas (abajo)
                    caras["tris"] += 2
                    continue
            else:
                ch = trozo_de(x, z)
            vs = [(P[k], uv[k], cols[k], n) for k in range(len(P))]
            # PS1: un cuadrilátero son los triángulos 0-1-2 y 1-3-2
            for tri in ((0, 1, 2), (1, 3, 2)) if len(P) == 4 else ((0, 1, 2),):
                t3 = tuple(vs[k] for k in tri)
                if bajo_mar and max(v[0][2] for v in t3) < nivel_agua - FUNDIDO_AGUA:
                    caras["negras"] += 1         # ya negro del todo, delante del fondo negro: no hace falta
                    continue
                if rot < 0:
                    por_grupo[(ch, clave)].append(t3)     # objeto de decorado: pequeño, sin trocear
                elif bajo_mar and max(v[0][2] for v in t3) < nivel_agua - 0.5:
                    por_grupo[(ch, clave)].append(t3)     # bajo el agua no se acerca la cámara: sin trocear
                    caras["bajo_agua"] += 1
                else:
                    por_grupo[(ch, clave)].extend(_partir(t3))
            caras["tris"] += len(P) - 2
            if not agua and abs(n[2]) < 0.7:
                paredes_tile[(x, z)][region] += 1
            # colisión: la geometría de verdad (_es_colision); el agua no (se hunde uno en ella)
            # (solo cerca de donde se anda: lo de dentro de la roca o lo alto de los riscos no lo pisa nadie y
            # hacía la colisión de un mapa de varios MB)
            # el agua de las casillas donde se anda (orillas, bajíos) se pisa, como en el King's Field: se anda por
            # la superficie y desde ella se sube a tierra; en el agua honda (casillas vacías) no hay suelo y se cae
            liso = (x, z) in datos.rampas or (x, z) in datos.planos
            if colision and rot == -1 - FUENTE_ID and abs(n[2]) <= 0.5:
                # la fuente: sus caras de los lados como pared (el pilón, de 1,1 m, no se sube ni se atraviesa)
                editor.geo.coll[trozo_de(x, z)]["wall"].append(list(P))
            if colision and rot >= 0 and (x, z) in cerca_suelo and (not agua or (x, z) in datos.suelo):
                tipo = _es_colision(P, n)
                en_borde = False
                al_otro = None
                if liso and tipo is None and abs(n[2]) <= 0.5:
                    # una cara en el borde de la casilla que da a otra que no es escalera: es la pared (la torre
                    # del caracol tiene la escalera pegada a su pared, hecha de bandas de 0,62 m)
                    bx0, by0 = editor.ox + (x + pad) * C, editor.oy + (z + pad) * C
                    for (dx, dz), sel, lim in (((-1, 0), 0, bx0), ((1, 0), 0, bx0 + C), ((0, -1), 1, by0),
                                               ((0, 1), 1, by0 + C)):
                        if all(abs(p[sel] - lim) < 0.06 for p in P):
                            vec_ = (x + dx, z + dz)
                            en_borde = vec_ not in datos.rampas and vec_ not in datos.planos
                            if en_borde:       # el punto al otro lado del borde (_decidir_cantos mira su suelo)
                                mcx = sum(p[0] for p in P) / len(P) + dx * 0.3
                                mcy = sum(p[1] for p in P) / len(P) + dz * 0.3
                                al_otro = (mcx, mcy)
                            break
                if liso and not en_borde and (tipo == "floor" or (tipo is None and abs(n[2]) <= 0.5)):
                    # la escalera va como rampa lisa (abajo): fuera sus peldaños y sus cantos (de 0,16 a 0,78 m);
                    # las piezas de pared de 1,25 m de esas casillas (la torre del caracol: la escalera va pegada
                    # a su pared) sí cuentan, o se cruzaba la pared de la torre y se caía uno
                    tipo = "nada"
                vec = [pisos.get((x + dx, z + dz)) for dx in (-1, 0, 1) for dz in (-1, 0, 1)]
                vec = [v for v in vec if v is not None]
                if tipo == "floor" and (x, z) not in datos.suelo:
                    if not vec or min(p[2] for p in P) > max(vec) + 1.0:
                        tipo = None
                # (las paredes van todas: recortarlas por la altura de los suelos vecinos dejó sin colisión la
                # torre del caracol, cuyas casillas tienen el suelo arriba del todo)
                chc = trozo_de(x, z)        # (el agua se dibuja en sus registros grandes; su colisión no)
                if tipo == "nada":
                    pass
                elif tipo:
                    editor.geo.coll[chc][tipo].append(list(P))
                elif tipo is None and abs(n[2]) <= 0.5:
                    cantos.append((chc, list(P), n, al_otro))   # ¿canto de escalón o pared? (_decidir_cantos)
    if colision:
        for (x, z), ((d, lo, hi), hh) in datos.rampas.items():
            base = (hh - h0) * ALTURA_M
            x0 = editor.ox + (x + pad) * C
            y0 = editor.oy + (z + pad) * C
            # alturas de las esquinas (x0,y0) (x1,y0) (x1,y1) (x0,y1): N sube hacia +y, E hacia +x
            e = {"N": (lo, lo, hi, hi), "S": (hi, hi, lo, lo), "E": (lo, hi, hi, lo), "W": (hi, lo, lo, hi)}[d]
            q = [(x0, y0, base + e[0]), (x0 + C, y0, base + e[1]), (x0, y0 + C, base + e[3]), (x0 + C, y0 + C, base + e[2])]
            editor.geo.coll[trozo_de(x, z)]["floor"].append(q)
        for (x, z), ((a, b, c0), hh) in datos.planos.items():
            base = (hh - h0) * ALTURA_M
            x0 = editor.ox + (x + pad) * C
            y0 = editor.oy + (z + pad) * C
            hz = lambda px, pz: base + c0 + a * px + b * pz
            q = [(x0, y0, hz(-1, -1)), (x0 + C, y0, hz(1, -1)), (x0, y0 + C, hz(-1, 1)), (x0 + C, y0 + C, hz(1, 1))]
            editor.geo.coll[trozo_de(x, z)]["floor"].append(q)
    lechos = [round(datos.fondos[k], 2) for k in datos.fondos if k not in datos.suelo and k not in datos.roca
              and k in datos.topes and datos.fondos[k] < datos.topes[k] - 1.5]
    # el fondo negro, donde las paredes ya han acabado de fundirse a negro (FUNDIDO_AGUA bajo el nivel del mar): ni
    # por encima (taparía lo que aún se ve) ni muy por debajo (se veía el pie de las paredes cortado)
    lecho_negro = (nivel_agua - FUNDIDO_AGUA - 0.05) if (lechos and nivel_agua is not None) else None
    # el agua y el vacío: sin pared invisible (el mapa portado va sin barandilla); bajo la superficie hay una
    # lámina "mortal" (lista hazard de la colisión, material 0-FF-FF: Player_CollideWithMap pone
    # ground_kills), como en el King's Field, donde caer al fondo del mar mataba
    for z in range(N_KF):
        for x in range(N_KF):
            vacia = (x, z) not in datos.suelo and (x, z) not in datos.roca
            if not vacia and (x, z) not in con_agua:
                continue
            tope = datos.topes.get((x, z))
            if tope is None:
                vec = [pisos.get((x + dx, z + dz)) for dx in (-1, 0, 1) for dz in (-1, 0, 1)]
                vec = [v for v in vec if v is not None]
                if not vec:
                    continue
                tope = min(vec)
            # el fondo de verdad: lo más bajo de los modelos de la casilla (el lecho del mar del King's Field)
            lecho = datos.fondos.get((x, z))
            if lecho is None or lecho > tope - 1.5:
                lecho = tope - 2.6
            if lecho_negro is not None:
                lecho = max(lecho, lecho_negro)      # se cae hasta el fondo negro, no más abajo
            x0 = editor.ox + (x + pad) * C
            y0 = editor.oy + (z + pad) * C
            ch = trozo_de(x, z)
            if vacia:
                # como en el King's Field: se cae al fondo y se muere al llegar. Suelo de colisión en el lecho y la
                # lámina mortal 1 m por encima (el 4 mata cuando la lámina queda entre los pies y 2,3 m por encima)
                hz = min(lecho + 1.0, tope - 0.3)
                editor.geo.coll[ch].setdefault("hazard", []).append(
                    [(x0, y0, hz), (x0 + C, y0, hz), (x0, y0 + C, hz), (x0 + C, y0 + C, hz)])
                editor.geo.coll[ch]["floor"].append(
                    [(x0, y0, lecho), (x0 + C, y0, lecho), (x0, y0 + C, lecho), (x0 + C, y0 + C, lecho)])
            if clave_negra is not None and lecho_negro is not None:
                # el fondo negro, justo por debajo del lecho: lo que se ve a través del agua en vez del mundo por
                # debajo; también bajo las casillas de orilla (agua en diagonal), que antes dejaban huecos
                negros.append((x, z, ch))
    # suelo en los huecos de las puertas y paredes secretas: a la altura del suelo de al lado, con su textura
    huecos = set(getattr(datos, "huecos_puerta", ())) | {k for k in suelos_secreta if k not in con_suelo}
    for (x, z) in sorted(huecos):
        vec = [(pisos[(x + dx, z + dz)], (x + dx, z + dz)) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
               if (x + dx, z + dz) in pisos]
        if not vec:
            continue
        h, k = min(vec)
        tex = suelo_tex.get(k) or next((suelo_tex[v[1]] for v in vec if v[1] in suelo_tex), None)
        x0 = editor.ox + (x + pad) * C
        y0 = editor.oy + (z + pad) * C
        q = [(x0, y0, h), (x0 + C, y0, h), (x0, y0 + C, h), (x0 + C, y0 + C, h)]
        if colision:
            editor.geo.coll[trozo_de(x, z)]["floor"].append(list(q))
        if tex:
            clave_t, u0, v0, du, dv = tex
            up = (0.0, 0.0, 1.0)
            vs = [(p, (u0 + du * (0.02 + 0.96 * ((p[0] - x0) / C)), v0 + dv * (0.02 + 0.96 * ((p[1] - y0) / C))),
                   editor.luzv(p, up, 0.55), up) for p in q]
            for tri in ((0, 2, 1), (1, 2, 3)):
                por_grupo[(trozo_de(x, z), clave_t)].append(tuple(vs[t] for t in tri))
    _juntar_mar(editor, mar, negros, clave_negra, lecho_negro, por_grupo, pad)
    editor.kf_pared_en = _pared_en(editor, atlas, paredes_tile, pad)
    editor.kf_puerta_en = _puerta_en(editor, datos, atlas, pad)
    if atlas.agua_usos:
        region = atlas.agua_usos.most_common(1)[0][0]
        idx, pal = _region_indices(datos.vram, *region)
        rep = 128 // idx.shape[0]
        atlas.agua = (np.tile(idx, (rep, rep))[:128, :128], pal)
    if colision:
        _decidir_cantos(editor, cantos)
        _quitar_paredes_altas(editor)
        _rampas_de_bordes(editor)
        _juntar_colision(editor)
    import sys
    print(f"kf_malla: {caras['tris']} caras, {caras['negras']} triángulos negros bajo el agua quitados, "
          f"(solo cerca del agua)", file=sys.stderr)
    global ULTIMAS_OCULTAS
    ULTIMAS_OCULTAS = caras["ocultas"]
    for (ch, clave), tris in por_grupo.items():
        for tira in tiras(tris):
            editor.geo.strip(ch, clave, tira)
    return plantillas, regiones_sin_sitio, caras["tris"]


def _indice_suelos(editor):
    C = 2.5
    tris = []
    for ch, kinds in editor.geo.coll.items():
        for P in kinds.get("floor", []):
            for tri in ((0, 1, 2), (1, 3, 2)) if len(P) == 4 else ((0, 1, 2),):
                tris.append(tuple(tuple(P[k]) for k in tri))
    indice = collections.defaultdict(list)
    for i, t in enumerate(tris):
        xs = [p[0] for p in t]
        ys = [p[1] for p in t]
        for gx in range(int(math.floor(min(xs) / C)), int(math.floor(max(xs) / C)) + 1):
            for gy in range(int(math.floor(min(ys) / C)), int(math.floor(max(ys) / C)) + 1):
                indice[(gx, gy)].append(i)

    def alturas(x, y):
        out = []
        for i in indice.get((int(math.floor(x / C)), int(math.floor(y / C))), ()):
            a, b, c = tris[i]
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / d
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / d
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) >= -1e-6:
                out.append(l1 * a[2] + l2 * b[2] + l3 * c[2])
        return out
    return alturas


def _quitar_paredes_altas(editor):
    """Fuera de la colisión las paredes que empiezan más de 2,6 m por encima de todo suelo de alrededor (dos
    casillas a cada lado, contando los suelos de verdad, la torre incluida): la cápsula del jugador (2,3 m) y la de
    los enemigos no llegan nunca. Es lo alto de los riscos y las montañas, y ocupaba mucho del mapa."""
    C = 2.5
    techo = {}
    for ch, kinds in editor.geo.coll.items():
        for P in kinds.get("floor", []):
            for p in P:
                k = (math.floor(p[0] / C), math.floor(p[1] / C))
                if p[2] > techo.get(k, -1e9):
                    techo[k] = p[2]
    alto = {}

    def tope(k):
        if k not in alto:
            vals = [techo[(k[0] + dx, k[1] + dy)] for dx in range(-2, 3) for dy in range(-2, 3)
                    if (k[0] + dx, k[1] + dy) in techo]
            alto[k] = max(vals) if vals else None
        return alto[k]
    quitadas = 0
    for ch, kinds in editor.geo.coll.items():
        quedan = []
        for P in kinds.get("wall", []):
            cx = sum(p[0] for p in P) / len(P)
            cy = sum(p[1] for p in P) / len(P)
            t = tope((math.floor(cx / C), math.floor(cy / C)))
            if t is not None and min(p[2] for p in P) > t + 2.6:
                quitadas += 1
                continue
            quedan.append(P)
        kinds["wall"] = quedan
    import sys
    print(f"kf_malla: {quitadas} paredes por encima de todo suelo cercano fuera de la colisión", file=sys.stderr)


def _decidir_cantos(editor, cantos):
    """Las caras verticales bajas (que no suben más de ESCALON_KF): son el canto de un escalón si justo detrás de su
    borde de arriba hay suelo a esa altura (y entonces no son pared: se suben, con rampa si hace falta); si no, son
    un trozo de pared y van como pared. Las paredes del King's Field están hechas de piezas de 1,25 m apiladas
    (la torre del caracol del nivel 0): tomadas como escalones se quedaba la torre sin colisión."""
    alturas = _indice_suelos(editor)
    paredes = 0
    # caras verticales por su sitio en planta (medio metro), con su pie y su plano: para ver si hay otra apilada
    # encima en el mismo plano (pared de piezas; los peldaños de una escalera están uno detrás de otro, no encima)
    bases = collections.defaultdict(list)

    def plano(P, n):
        ln = math.hypot(n[0], n[1]) or 1.0
        ux, uy = n[0] / ln, n[1] / ln
        cx = sum(p[0] for p in P) / len(P)
        cy = sum(p[1] for p in P) / len(P)
        return cx, cy, ux, uy
    for ch, P, n, _ in cantos:
        cx, cy, ux, uy = plano(P, n)
        bases[(round(cx * 2), round(cy * 2))].append((min(p[2] for p in P), cx, cy, ux, uy))
    for ch, kinds in editor.geo.coll.items():
        for P in kinds.get("wall", []):
            a, b, c = P[0], P[1], P[2]
            nn = _norm(_cross(_sub(b, a), _sub(c, a)))
            if abs(nn[2]) > 0.5:
                continue
            cx, cy, ux, uy = plano(P, nn)
            bases[(round(cx * 2), round(cy * 2))].append((min(p[2] for p in P), cx, cy, ux, uy))
    for ch, P, n, al_otro in cantos:
        zs = [p[2] for p in P]
        if max(zs) - min(zs) < 0.05:
            continue
        if al_otro is not None and any(min(zs) - 0.3 <= h <= max(zs) + 0.3 for h in alturas(*al_otro)):
            continue        # borde de una escalera con suelo al otro lado a su altura (un rellano): se pasa
        ln = math.hypot(n[0], n[1]) or 1.0
        ux, uy = n[0] / ln, n[1] / ln
        tope = max(zs)
        arriba = [p for p in P if p[2] > tope - 0.05]
        cx = sum(p[0] for p in arriba) / len(arriba)
        cy = sum(p[1] for p in arriba) / len(arriba)
        mx = sum(p[0] for p in P) / len(P)
        my = sum(p[1] for p in P) / len(P)
        # otra pieza de pared justo encima y en su mismo plano (las paredes del King's Field son piezas apiladas)
        k0 = (round(mx * 2), round(my * 2))
        apilada = any(abs(b - tope) < 0.1 and abs(abs(ux * bx + uy * by) - 1) < 0.05
                      and abs((bxc - mx) * ux + (byc - my) * uy) < 0.08
                      for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                      for (b, bxc, byc, bx, by) in bases.get((k0[0] + dx, k0[1] + dy), ()))
        escalon = False
        if not apilada:
            for lado in (-1, 1):              # detrás de la cara (o delante, si la normal va al revés)
                if any(abs(h - tope) < 0.15 for h in alturas(cx + lado * ux * 0.3, cy + lado * uy * 0.3)):
                    escalon = True
                    break
        if not escalon:
            editor.geo.coll[ch]["wall"].append(P)
            paredes += 1
    import sys
    print(f"kf_malla: {len(cantos)} caras verticales bajas, {paredes} son trozos de pared", file=sys.stderr)


def _rampas_de_bordes(editor):
    """Rampas de colisión en cada borde de suelo que tiene otro suelo de 0,7 a ESCALON_KF m más abajo justo al lado
    (de la orilla del agua a tierra, de un peldaño de 0,78 a otro...). El 4 solo sube 75 cm buscando suelo, y sin
    rampa se metía dentro del escalón y caía al vacío. Sale de los suelos, no de los cantos: a muchos escalones del
    King's Field les falta la cara del canto (la tapa la casilla de al lado o no se ve)."""
    C = 2.5
    tris = []
    for ch, kinds in editor.geo.coll.items():
        for P in kinds.get("floor", []):
            for tri in ((0, 1, 2), (1, 3, 2)) if len(P) == 4 else ((0, 1, 2),):
                tris.append((ch, tuple(tuple(P[k]) for k in tri)))
    indice = collections.defaultdict(list)
    for i, (_, t) in enumerate(tris):
        xs = [p[0] for p in t]
        ys = [p[1] for p in t]
        for gx in range(int(math.floor(min(xs) / C)), int(math.floor(max(xs) / C)) + 1):
            for gy in range(int(math.floor(min(ys) / C)), int(math.floor(max(ys) / C)) + 1):
                indice[(gx, gy)].append(i)

    def alturas(x, y):
        out = []
        for i in indice.get((int(math.floor(x / C)), int(math.floor(y / C))), ()):
            a, b, c = tris[i][1]
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / d
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / d
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) >= -1e-6:
                out.append(l1 * a[2] + l2 * b[2] + l3 * c[2])
        return out
    hechas = set()
    nuevas = 0
    for ch, t in tris:
        for (a, b, c) in ((t[0], t[1], t[2]), (t[1], t[2], t[0]), (t[2], t[0], t[1])):
            ex, ey = b[0] - a[0], b[1] - a[1]
            L = math.hypot(ex, ey)
            if L < 0.2:
                continue
            ox, oy = ey / L, -ex / L                     # perpendicular hacia fuera (lejos de c)
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            if (c[0] - mx) * ox + (c[1] - my) * oy > 0:
                ox, oy = -ox, -oy
            hz = (a[2] + b[2]) / 2
            hs = alturas(mx + ox * 0.3, my + oy * 0.3)
            if any(hz - 0.7 <= h <= hz + 0.75 for h in hs):
                continue                                  # sigue el suelo (o se sube andando)
            abajo = [h for h in hs if hz - ESCALON_KF <= h < hz - 0.7]
            if not abajo:
                continue
            h2 = max(abajo)
            clave = (round(mx, 2), round(my, 2), round(hz, 2))
            if clave in hechas:
                continue
            hechas.add(clave)
            dd = hz - h2
            pa = (a[0] + ox * dd, a[1] + oy * dd, h2)
            pb = (b[0] + ox * dd, b[1] + oy * dd, h2)
            editor.geo.coll[ch]["floor"].append([pa, pb, a, b])
            nuevas += 1
    import sys
    print(f"kf_malla: {nuevas} rampas de escalón sacadas de los bordes de los suelos", file=sys.stderr)


def _juntar_colision(editor):
    """Junta las caras de colisión que comparten arista en tiras largas (como las del dibujo): cada tira lleva 0x20
    bytes de cabecera y cada punto 16, así que caras sueltas hacían la colisión de un mapa portado de varios MB."""
    for ch, kinds in editor.geo.coll.items():
        for kind in ("wall", "floor"):
            polys = kinds.get(kind) or []
            tris = []
            for P in polys:
                vs = [(tuple(p), (0.0, 0.0), (0, 0, 0), None) for p in P]
                for tri in ((0, 1, 2), (1, 3, 2)) if len(vs) == 4 else ((0, 1, 2),):
                    tris.append(tuple(vs[k] for k in tri))
            kinds[kind] = [[v[0] for v in tira] for tira in tiras(tris)]


def _rampa_escalon(P, n):
    """Un escalón del King's Field (canto vertical de 0,7 a ESCALON_KF m) no se sube andando en el 4, que solo busca
    el suelo 75 cm por encima de los pies: delante del canto se pone una rampa de colisión a 45 grados, del pie
    (desplazado hacia el lado bajo, al que mira la cara) hasta el borde de arriba. Así se sube sin depender de
    ningún parche y sin colarse dentro del escalón. None si la cara no es un canto así."""
    zs = [p[2] for p in P]
    alto = max(zs) - min(zs)
    if not 0.7 < alto <= ESCALON_KF or len(P) != 4:
        return None
    arriba = [p for p in P if p[2] > max(zs) - 0.05]
    abajo = [p for p in P if p[2] < min(zs) + 0.05]
    if len(arriba) != 2 or len(abajo) != 2:
        return None
    ln = math.hypot(n[0], n[1]) or 1.0
    ux, uy = n[0] / ln, n[1] / ln
    d = alto * 1.0
    pie = [(p[0] + ux * d, p[1] + uy * d, p[2]) for p in abajo]
    # en el mismo orden a lo largo del canto: a0 b0 abajo, a1 b1 arriba
    a, b = pie
    c, e = sorted(arriba, key=lambda q: (q[0] - a[0]) ** 2 + (q[1] - a[1]) ** 2)
    return [a, b, c, e]


def _es_colision(P, n):
    """'floor' (cara que mira arriba), 'wall' (cara vertical que sube más de ESCALON_KF: los cantos de los escalones
    del King's Field, de 0,78 m, no; el 4 los sube con el parche del escalón) o None."""
    if n[2] > 0.5:           # hasta 60 grados (las laderas de 45 del King's Field se andan)
        return "floor"
    zs = [p[2] for p in P]
    if abs(n[2]) <= 0.5 and max(zs) - min(zs) > ESCALON_KF:
        return "wall"
    return None


def _trozos(editor, datos, pad, h0):
    """Los registros del mapa: trozos de 8 x 8 casillas, y de 4 x 4 donde la colisión de verdad pasa de los puntos
    que caben en el scratchpad (1008: Collision_TransformMeshPoints los escribe a partir de 0x70000100)."""
    C = editor.celda
    puntos = collections.defaultdict(set)
    for (x, z, t, elev, rot) in datos.capas:
        verts, prims = datos.objs[t]
        ox = editor.ox + (x + pad + 0.5) * C
        oy = editor.oy + (z + pad + 0.5) * C
        oz = (elev - h0) * ALTURA_M
        mundo = []
        for v in verts:
            gx, gy, gz = _girar(v, rot)
            mundo.append((round(ox + gx * ESCALA, 3), round(oy + gz * ESCALA, 3), round(oz - gy * ESCALA, 3)))
        for tpage, clut, uvs, refs, nrm_ps in prims:
            if tpage is None or (tpage >> 7) & 3:
                continue
            if AGUA_ANIMADA and es_agua(datos, (tpage, clut) + _region(uvs)) and (x, z) not in datos.suelo:
                continue                     # el agua honda no tiene colisión (la de los bajíos sí se pisa)
            P = [mundo[r] for r in refs]
            if nrm_ps is not None:
                nx, ny, nz = _girar(nrm_ps, rot)
                n = (nx / 4096.0, nz / 4096.0, -ny / 4096.0)
            else:
                n = _norm(_cross(_sub(P[1], P[0]), _sub(P[2], P[0])))
            if _es_colision(P, n):
                puntos[(x + pad, z + pad)].update(P)
    for z in range(N_KF):            # el lecho y la lámina mortal de las casillas de agua honda
        for x in range(N_KF):
            if (x, z) not in datos.suelo and (x, z) not in datos.roca:
                puntos[(x + pad, z + pad)].update(((x, z, 0), (x + 1, z, 0), (x, z + 1, 0), (x + 1, z + 1, 0),
                                                   (x, z, 1), (x + 1, z, 1), (x, z + 1, 1), (x + 1, z + 1, 1)))
    # trozos de 8, y los que no caben, de 4; y si aún no, de 2 (lo más denso de los niveles 1 y 3)
    def cuenta(i0, j0, lado):
        tot = set()
        for i in range(i0, i0 + lado):
            for j in range(j0, j0 + lado):
                tot |= puntos.get((i, j), set())
        return len(tot)
    grande = {}
    for (i, j) in puntos:
        k8 = (i // 8, j // 8)
        if k8 not in grande:
            grande[k8] = cuenta(k8[0] * 8, k8[1] * 8, 8) > PUNTOS_TROZO
    medio = {}
    for (i, j) in puntos:
        if grande[(i // 8, j // 8)]:
            k4 = (i // 4, j // 4)
            if k4 not in medio:
                medio[k4] = cuenta(k4[0] * 4, k4[1] * 4, 4) > PUNTOS_TROZO

    def f(x, z):
        i, j = x + pad, z + pad
        forzado = FORZAR_PARTIR.get((i // 8, j // 8))
        if forzado == 2:
            return ("I", i // 2, j // 2)
        if not grande.get((i // 8, j // 8)) and not forzado:
            return ("G", i // 8, j // 8)
        if not medio.get((i // 4, j // 4)):
            return ("H", i // 4, j // 4)
        return ("I", i // 2, j // 2)
    f.partidos = sum(grande.values())
    return f


def _pared_en(editor, atlas, paredes_tile, pad):
    """Función pos -> ((tbp, cbp, tbw, W, H, psm), (x, y, lado, W, H) en el hueco) con la textura de pared del
    King's Field más usada alrededor de esa casilla, para que las paredes que se abren no se noten."""
    def f(pos):
        C = editor.celda
        x = int(math.floor((pos[0] - editor.ox) / C)) - pad
        z = int(math.floor((pos[1] - editor.oy) / C)) - pad
        votos = collections.Counter()
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                votos.update(paredes_tile.get((x + dx, z + dz), {}))
        for region, _ in votos.most_common():
            if region in atlas.sitio:
                h, ax, ay, lado, cbp = atlas.sitio[region]
                fh = h["f"]
                return ((fh["TBP"], cbp, fh["TBW"], fh["W"], fh["H"], 0x14), (ax, ay, lado, fh["W"], fh["H"]))
        return None
    return f


def modelo_mo(datos, oid):
    """(verts, prims) del modelo de MO.T del objeto oid (entrada 128 + id), o None."""
    import struct
    mo = getattr(datos, "mo", None)
    if not mo or 128 + oid >= len(mo):
        return None
    d = mo[128 + oid]
    if not d or len(d) <= 16:
        return None
    tmd = struct.unpack_from("<I", d, 8)[0]
    if tmd >= len(d) - 12 or d[tmd] != 0x41:
        return None
    try:
        ob = kf2_tex.objetos_tmd(d[tmd:], por_8=False)
    except (ValueError, struct.error):
        return None
    return ob[0] if ob and ob[0][0] and ob[0][1] else None


def _puerta_en(editor, datos, atlas, pad):
    """Función pos -> (textura, cuadro en el hueco) de la puerta del King's Field que hay en esa casilla: la
    textura que más superficie cubre en su modelo (MO.T). La puerta del 4 que se pone (un bloque que sube, como
    las puertas del King's Field) la lleva, en vez de la reja del 4. None si no hay puerta ahí."""
    tex = {}
    cache = {}
    for (col, fila, oid) in getattr(datos, "puertas_kf", ()):
        if oid not in cache:
            cache[oid] = None
            m = modelo_mo(datos, oid)
            if m:
                area = collections.Counter()
                for tpage, clut, uvs, refs, nrm in m[1]:
                    if tpage is None or (tpage >> 7) & 3:
                        continue
                    cu, cv, lado = _region(uvs)
                    us, vs = [u for u, _ in uvs], [v for _, v in uvs]
                    area[(tpage, clut, cu, cv, lado)] += (max(us) - min(us) + 1) * (max(vs) - min(vs) + 1)
                for region, _ in area.most_common():
                    if region not in atlas.sitio:
                        img, pal = _region_indices(datos.vram, *region)
                        if not atlas.poner(region, img, pal):
                            continue
                    h, ax, ay, lado, cbp = atlas.sitio[region]
                    fh = h["f"]
                    cache[oid] = ((fh["TBP"], cbp, fh["TBW"], fh["W"], fh["H"], 0x14), (ax, ay, lado, fh["W"], fh["H"]))
                    break
        if cache[oid]:
            tex[(col, fila)] = cache[oid]

    def f(pos):
        C = editor.celda
        x = (pos[0] - editor.ox) / C - pad - 0.5
        z = (pos[1] - editor.oy) / C - pad - 0.5
        mejor, d = None, 1.5 ** 2
        for (cx, cz), t in tex.items():
            dd = (cx - x) ** 2 + (cz - z) ** 2
            if dd < d:
                mejor, d = t, dd
        return mejor
    return f


def _juntar_mar(editor, mar, negros, clave_negra, lecho_negro, por_grupo, pad):
    """El mar abierto (un cuadrado de agua por casilla, 3000 en el nivel 0) y el fondo negro de debajo, de 2 x 2
    casillas en un cuadrado de 5 m: la cuarta parte de triángulos. El agua usa su propia textura animada, que se
    repite sola (la casilla ocupa media textura: dos casillas, una entera). Más grande no: el 4 tira los
    triángulos que se salen mucho de la pantalla cerca de la cámara y el agua desaparecería a los pies."""
    C = editor.celda
    hechos = set()
    junt = 0

    def bloque(x, z):
        i, j = (x + pad) // 2 * 2 - pad, (z + pad) // 2 * 2 - pad
        return [(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)]
    for (x, z) in sorted(mar):
        if (x, z) in hechos:
            continue
        cas = bloque(x, z)
        alturas = {round(mar[k][0][0][2], 2) for k in cas if k in mar}
        if all(k in mar and k not in hechos for k in cas) and len(alturas) == 1 and \
                len({mar[k][3] for k in cas}) == 1:
            P, cols, n, clave = mar[cas[0]]
            i0, j0 = cas[0]
            cx = editor.ox + (i0 + pad + 1.0) * C           # centro del bloque de 2 x 2
            cy = editor.oy + (j0 + pad + 1.0) * C
            tx = editor.ox + (i0 + pad + 0.5) * C           # centro de la casilla de la que se copia el orden
            ty = editor.oy + (j0 + pad + 0.5) * C
            vs = []
            for p, c in zip(P, cols):
                sx = 1 if p[0] > tx else -1
                sy = 1 if p[1] > ty else -1
                q = (cx + sx * C, cy + sy * C, p[2])
                col = editor.luzv(q, n, 0.0)
                m = editor.color_en(q[0], q[1])
                col = (col[0] * m[0] * OSCURO_AGUA, col[1] * m[1] * OSCURO_AGUA, col[2] * m[2] * OSCURO_AGUA, 0x40)
                vs.append((q, ((sx + 1) / 2, (sy + 1) / 2), col, n))
            ch = ("A", (i0 + pad) // TROZO_AGUA, (j0 + pad) // TROZO_AGUA)
            for tri in ((0, 1, 2), (1, 3, 2)):
                por_grupo[(ch, clave)].append(tuple(vs[k] for k in tri))
            hechos.update(cas)
            junt += 1
    for (x, z), (P, cols, n, clave) in mar.items():
        if (x, z) in hechos:
            continue
        ch = ("A", (x + pad) // TROZO_AGUA, (z + pad) // TROZO_AGUA)
        tx = editor.ox + (x + pad + 0.5) * C
        ty = editor.oy + (z + pad + 0.5) * C
        vs = [(p, ((1 if p[0] > tx else 0) * 0.5, (1 if p[1] > ty else 0) * 0.5), c, n) for p, c in zip(P, cols)]
        for tri in ((0, 1, 2), (1, 3, 2)):
            por_grupo[(ch, clave)].append(tuple(vs[k] for k in tri))
    # el fondo negro: igual, de 2 x 2 donde se puede (mismo registro)
    if clave_negra is not None and lecho_negro is not None:
        k_tex, u0, v0 = clave_negra
        fn = lecho_negro
        up = (0.0, 0.0, 1.0)
        negro = (0.0, 0.0, 0.0)
        por_casilla = {(x, z): ch for x, z, ch in negros}
        hechos_n = set()
        for (x, z), ch in sorted(por_casilla.items()):
            if (x, z) in hechos_n:
                continue
            cas = bloque(x, z)
            if all(k in por_casilla and k not in hechos_n and por_casilla[k] == ch for k in cas):
                i0, j0 = cas[0]
                lado = 2
            else:
                i0, j0, lado = x, z, 1
                cas = [(x, z)]
            x0 = editor.ox + (i0 + pad) * C
            y0 = editor.oy + (j0 + pad) * C
            L = lado * C
            editor.geo.quad(ch, k_tex, (x0, y0, fn), (x0 + L, y0, fn), (x0 + L, y0 + L, fn), (x0, y0 + L, fn),
                            *[(u0, v0)] * 4, *[negro] * 4, up, cerca=False)
            hechos_n.update(cas)
    import sys
    print(f"kf_malla: mar de {len(mar)} casillas en {junt} cuadrados de 2 x 2 y {len(mar) - 4 * junt} sueltas",
          file=sys.stderr)


def _interior(editor, p, cache):
    """Cuánto 'bajo techo' está un punto (0 fuera, 0,55 dentro), interpolado entre las cuatro casillas que lo
    rodean: así no hay saltos de luz de golpe en el borde de cada casilla con techo."""
    C = editor.celda
    fx = (p[0] - editor.ox) / C - 0.5
    fy = (p[1] - editor.oy) / C - 0.5
    i0, j0 = int(math.floor(fx)), int(math.floor(fy))
    tx, ty = fx - i0, fy - j0

    def v(i, j):
        k = (i, j)
        if k not in cache:
            ce = editor.celda_en(i, j)
            cache[k] = 0.55 if isinstance(ce, dict) and ce.get("techo") is not None else 0.0
        return cache[k]
    return ((v(i0, j0) * (1 - tx) + v(i0 + 1, j0) * tx) * (1 - ty)
            + (v(i0, j0 + 1) * (1 - tx) + v(i0 + 1, j0 + 1) * tx) * ty)


def _visible(P, nrm_ps, rot, editor, pad, datos):
    """Una cara que mira a una casilla de roca (o fuera del mapa) no se ve desde ningún sitio donde se pueda estar."""
    if nrm_ps is None:
        return True
    nx, ny, nz = _girar(nrm_ps, rot)
    n = (nx / 4096.0, nz / 4096.0, -ny / 4096.0)
    if abs(n[2]) > 0.7:          # suelos y techos: se quedan
        return True
    cx = sum(p[0] for p in P) / len(P) + n[0] * 0.4
    cy = sum(p[1] for p in P) / len(P) + n[1] * 0.4
    x = int(math.floor((cx - editor.ox) / editor.celda)) - pad
    z = int(math.floor((cy - editor.oy) / editor.celda)) - pad
    if not (0 <= x < N_KF and 0 <= z < N_KF):
        return False
    if (x, z) not in datos.roca:
        return True
    # la roca vecina solo la tapa si llega por lo menos hasta arriba de la cara (si no, la parte alta de un risco
    # que mira a una roca más baja se ve desde lejos: faltaban caras en las paredes altas)
    if OCULTAS_ESTRICTO:
        return False
    tope = datos.topes.get((x, z))
    return tope is None or max(p[2] for p in P) > tope + 0.05


LADO_MAXIMO = 3.7     # m: TROZO_MAX del generador (2,6) en los lados de una casilla; su diagonal (3,54) no se parte


def _partir(t, nivel=0):
    """Parte un triángulo por la mitad de su lado más largo hasta que ningún lado pase de LADO_MAXIMO."""
    def d(a, b):
        return math.dist(a[0], b[0])
    lados = [(d(t[0], t[1]), 0, 1, 2), (d(t[1], t[2]), 1, 2, 0), (d(t[2], t[0]), 2, 0, 1)]
    largo, i, j, k = max(lados)
    if largo <= LADO_MAXIMO or nivel > 6:
        return [t]
    a, b, c = t[i], t[j], t[k]
    m = (tuple((a[0][q] + b[0][q]) / 2 for q in range(3)), tuple((a[1][q] + b[1][q]) / 2 for q in range(2)),
         tuple((a[2][q] + b[2][q]) / 2 for q in range(len(a[2]))), a[3])
    # mismo sentido de giro que el original: (a, m, c) y (m, b, c)
    return _partir((a, m, c), nivel + 1) + _partir((m, b, c), nivel + 1)


def _clave_v(v):
    p, uv, c, _ = v
    # sin el color: dos caras que comparten vértice se suavizan ahí (sombreado de Gouraud, como el 4)
    return (round(p[0], 3), round(p[1], 3), round(p[2], 3), round(uv[0], 4), round(uv[1], 4))


def tiras(tris):
    """Junta triángulos que comparten arista (mismo vértice: posición, UV y color) en tiras: cada triángulo
    de más cuesta un vértice en vez de tres. Codicioso, como los stripifiers sencillos."""
    claves = [tuple(_clave_v(v) for v in t) for t in tris]
    por_arista = collections.defaultdict(list)
    for i, k in enumerate(claves):
        for a, b in ((0, 1), (1, 2), (2, 0)):
            por_arista[frozenset((k[a], k[b]))].append(i)
    usado = [False] * len(tris)
    out = []
    for i0 in range(len(tris)):
        if usado[i0]:
            continue
        usado[i0] = True
        t = tris[i0]
        k = claves[i0]
        tira, ktira = [t[0], t[1], t[2]], [k[0], k[1], k[2]]
        while True:
            a, b = ktira[-2], ktira[-1]
            sig = None
            for j in por_arista[frozenset((a, b))]:
                if not usado[j]:
                    sig = j
                    break
            if sig is None:
                break
            usado[sig] = True
            kj = claves[sig]
            tercero = next(q for q in range(3) if kj[q] not in (a, b))
            tira.append(tris[sig][tercero])
            ktira.append(kj[tercero])
        out.append(tira)
    return out


def inyectar(tex_blob, atlas, log=None):
    """Escribe en el bloque de texturas del 099.map el atlas (índices de 4 bits de cada hueco) y sus paletas."""
    import kf4_tex as kt
    blob = bytearray(tex_blob)
    vram, ups = kt.upload_map_textures(bytes(blob), 0, len(blob))
    vram0 = vram.copy()
    usados = 0
    for h in atlas.huecos:
        if len(h["libres"]) == (h["f"]["W"] // CELDA_ATLAS) * (h["f"]["H"] // CELDA_ATLAS):
            continue                                   # hueco sin usar: se queda la textura del 4
        f = h["f"]
        a, alto = kf2_tex._direcciones4(f["TBP"], f["TBW"], f["W"], f["H"])
        idx = h["img"]
        bajo = ~alto
        vram[a[bajo]] = (vram[a[bajo]] & 0xF0) | idx[bajo]
        vram[a[alto]] = (vram[a[alto]] & 0x0F) | (idx[alto] << 4)
        usados += 1
    for cbp, pal in atlas.paletas.items():
        ca = kt.addr32(cbp, 1, *np.mgrid[0:2, 0:8][::-1]).reshape(-1)
        for k in range(4):
            vram[ca + k] = pal[:, k]
    if atlas.agua is not None:
        idx, pal = atlas.agua
        vram[_direcciones8(AGUA_SRC, 2, 128, 128)] = idx.astype(np.uint8)
        # paleta de 256 en CSM1 (16 x 16, con el cambio 8-15 <-> 16-23): solo se usan las 16 primeras
        y, x = np.mgrid[0:16, 0:16]
        ca = kt.addr32(AGUA_CLUT, 1, x, y).reshape(-1)
        orden = np.arange(256)
        sw = orden.copy()
        sw[(orden & 0x18) == 0x08] += 8
        sw[(orden & 0x18) == 0x10] -= 8
        p256 = np.zeros((256, 4), np.uint8)
        p256[:16] = pal
        p256[16:, 3] = 0x80
        tabla = p256[sw]
        for k in range(4):
            vram[ca + k] = tabla[:, k]
        # el destino ya con el agua quieta: si el juego no la anima, al menos se ve el agua
        rgba = pal[idx]
        y, x = np.mgrid[0:128, 0:128]
        ad = kt.addr32(AGUA_DST, 2, x, y).reshape(-1)
        for k in range(4):
            vram[ad + k] = rgba[..., k].reshape(-1)
    for u in ups:
        y, x = np.mgrid[u["y"]:u["y"] + u["h"], u["x"]:u["x"] + u["w"]]
        a = kt.addr32(u["dbp"], max(1, u["dbw"]), x, y).reshape(-1)
        # solo los bytes que ha cambiado el atlas: donde dos subidas se pisan (el paquete 2 y el 4 en 0x3BC0) cada
        # una conserva lo suyo, que es lo que lee el juego según el momento (las nubes del cielo salen de ahí)
        a4 = np.stack([(a + k) % kt.VRAM_BYTES for k in range(4)], -1).reshape(-1)
        n = min(len(a4), u["bytes"])
        a4 = a4[:n]
        cambio = vram[a4] != vram0[a4] if ESCRITURA_PARCIAL else np.ones(len(a4), bool)
        if not cambio.any():
            continue
        o = u["offset"] + 128
        viejo = np.frombuffer(bytes(blob[o:o + n]), np.uint8)
        blob[o:o + n] = np.where(cambio, vram[a4], viejo).astype(np.uint8).tobytes()
    if log is not None:
        log.append(f"Texturas del King's Field: {len(atlas.sitio)} regiones en {usados} huecos, "
                   f"{len(atlas.paletas)} paletas propias")
    return bytes(blob)


def _direcciones8(bp, bw, w, h):
    """Byte de la VRAM de cada píxel de una textura PSMT8 (como kf4_tex.read8)."""
    import kf4_tex as kt
    y, x = np.mgrid[0:h, 0:w]
    bw2 = max(1, bw >> 1)
    page = x // 128 + (y // 64) * bw2
    px, py = x % 128, y % 64
    block = kt.BLOCK8[px // 16 + (py // 16) * 8]
    bx, by = px % 16, py % 16
    col = by // 4
    cy = by % 4
    cw = kt.COLW8[col & 1, bx + cy * 16]
    cb = kt.COLB8[bx + cy * 16]
    a = bp * 256 + ((page * 2048 + block * 64 + col * 16 + cw) * 4) + cb
    return a % kt.VRAM_BYTES


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v):
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / l, v[1] / l, v[2] / l)
