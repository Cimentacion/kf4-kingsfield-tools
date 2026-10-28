#!/usr/bin/env python3
"""
kf1_objetos.py - Enemigos y objetos de un nivel de King's Field (PS1, el KF2 japonés) para el editor del 4.

Cada nivel tiene en FDAT.T la entrada 3n+1 con su base de datos (formato de KFModTool, IvanDSM/KingsFieldRE):
  u32 tamaño + 40 clases de enemigo (byte 0 = modelo) y sus estados
  u32 tamaño + 200 enemigos de 16 bytes:
      modo de reaparición, clase, giro fijo, casilla X, casilla Y, % reaparición, objeto que suelta, capa,
      u16 giro, s16 fino X, s16 fino Y, s16 fino Z    (fino: 0..2047 dentro de la casilla)
  u32 tamaño + 350 objetos de 24 bytes:
      capa, casilla X, casilla Y, ?, u16 id, u16 giro, s16 fino X, Y, Z, 10 bytes de parámetros
  u32 tamaño + 128 efectos

Aquí se traduce cada enemigo a un registro de chr.prm del 4 que se le parece, y cada objeto que se coge
(armas, armaduras, hierbas, llaves...) a un objeto del 4.
"""

import collections
import math
import struct

CELDA_M = 2.5

# --- enemigos: modelo de KF (EntityMeshID) -> (nombre, registro de chr.prm del 4, vuela) ---
# (el 9 no se pone: es una llamita estática de 1 punto de experiencia que hay a montones por los niveles)
ENEMIGOS = {
    0: ("Green Slime", 2, False), 12: ("Green Slime", 2, False), 13: ("Green Slime", 2, False),
    19: ("Green Slime", 2, False), 1: ("Poison Slime", 3, False),
    2: ("Sigill", 6, False),                       # araña
    4: ("Baltail", 16, False),                     # salamandra
    6: ("Sting Fly", 10, True),                    # murciélago de sangre
    10: ("Ghost", 85, True),                       # segador
    11: ("Reik", 24, False),                       # armadura viviente
    14: ("Head Eater", 18, False),                 # phagos
    15: ("Mogle", 12, False),                      # critter
    16: ("Snail", 63, False),                      # caracol gigante (MO.T[16]): kf4_caracol, registro 63 nuevo
    34: ("Copper Knight", 24, False),
    17: ("Soldier", 93, False), 18: ("Archer", 92, False),
    21: ("Skeleton", 77, False),               # el esqueleto de verdad (kf4_esqueleto: registro 77 nuevo) 44: ("Skeleton of One-Eyed Giant", 58, False),
    22: ("Termite", 11, False), 25: ("Giant Termite", 11, False), 47: ("Mecha Termite", 11, False),
    23: ("Kald", 56, False),                       # muerto viviente
    24: ("Psythe", 85, True),
    26: ("Red Spike Ball", 66, True),              # malicia
    27: ("Log Stalker", 12, False),
    28: ("Demon Lord", 58, False), 46: ("Mecha Demon Lord", 58, False),   # esqueleto alto (no el jefe)
    29: ("Kraken", 65, False),                    # el pulpo de verdad (kf4_pulpo: registro 48 nuevo del chr.prm)
    31: ("Earth Elemental", 68, False),
    32: ("Refma", 66, True), 51: ("Refma", 66, True),
    33: ("Tarn", 58, False),                       # esqueleto alto (el gigante es un jefe)
    35: ("Dias Bagil", 24, False),
    39: ("Guyra", 24, False),                      # armadura viviente (el Earth King es un jefe)
    40: ("Salamander", 16, False),
    42: ("Billent", 81, False),                    # larva
    50: ("Bitt", 10, True),
    107: ("Dragon Grass", 49, False),              # flor oscura
}
# vida de cada registro del 4 (chr.prm +0x0A), para repartir los que no caben entre los que sí
VIDA = {77: 175, 65: 125, 63: 75, 48: 400, 13: 200, 2: 60, 3: 60, 6: 100, 10: 54, 11: 105, 12: 750, 16: 550, 18: 1, 19: 600, 24: 1800, 32: 3000, 34: 4500,
        39: 500, 40: 1400, 49: 500, 50: 250, 56: 210, 58: 800, 66: 1300, 67: 900, 68: 900, 73: 3800, 75: 5500,
        81: 205, 85: 300, 92: 200, 93: 540}
# jefes y bichos enormes del 4: cuelgan el juego al cargar el mapa (probado con el 34, Earth King, y el 75,
# Greater Demon); si algún modelo de KF apunta a uno, se cambia por la armadura viviente. Los escarabajos 19 y 39
# también cuelgan (probado: solo 8 del 39 y no carga); los termitas son el escarabajo 11, el de 099
JEFES = {19, 39, 15, 17, 20, 22, 23, 32, 34, 45, 47, 55, 57, 61, 64, 71, 72, 73, 74, 75, 76, 78, 138, 151, 155, 156, 157,
         158, 159}
MAX_TIPOS = 12         # tipos de enemigo por mapa (con el hueco de pool 0xFF el 4 los carga y descarga según cerca)
MAX_ENEMIGOS = 120     # el 4 admite 128 por mapa (entity_pool[2][0x80]) y 60 activos a la vez (los cercanos)

# --- objetos que se cogen: id de KF -> objeto del 4 (item_nam.prm) ---
OBJETOS = {
    # armas
    0: 169, 1: 156, 2: 164, 3: 199, 4: 202, 5: 165, 6: 205, 7: 155, 8: 155, 9: 187, 10: 186, 11: 176,
    12: 168, 13: 196, 14: 167, 15: 186, 16: 207, 17: 210, 18: 155, 19: 155, 20: 155,
    # cascos
    21: 257, 22: 261, 23: 256, 24: 271, 25: 264, 26: 274, 27: 251,
    # cuerpo
    28: 280, 29: 286, 30: 296, 31: 295, 32: 298, 33: 276,
    # escudos
    34: 223, 35: 226, 36: 240, 37: 240, 38: 243, 39: 246, 40: 221,
    # brazos
    41: 307, 42: 304, 43: 319, 44: 314, 45: 311, 46: 301,
    # pies
    47: 331, 48: 336, 49: 334, 50: 346, 51: 341, 52: 328,
    # anillos, collares
    53: 355, 54: 371, 55: 363, 56: 356, 57: 372, 58: 361, 59: 351,
    # consumibles y demás
    70: 368, 71: 32, 72: 114, 73: 34, 74: 7, 75: 9, 76: 13, 77: 15, 78: 16, 79: 17, 80: 18, 81: 15,
    82: 14, 85: 130, 90: 71, 91: 74, 92: 72, 93: 73, 94: 75, 95: 76, 96: 70, 97: 70,
    98: 351, 110: 6, 117: 145, 118: 145, 119: 6,
}
COFRES = (120, 121, 122, 123)       # tapas y cuerpos de cofre
GUARDADOS = {230}            # el cristal de guardar del King's Field (las S del mapa): la piedra de guardado del IV
GUARDADO_DELANTE = 1.0       # m delante de la pared donde estaba el cristal
PUERTAS = {125, 126, 127, 128, 129, 132, 133, 134, 135, 139, 140, 194}
SECRETAS = {130, 131, 138, 205, 209, 214}
# de esas, las que son una pared con un hueco (nicho) en su cara: modelo fijo, no se abren (van como decorado,
# kf_malla); las otras (130 SecretDoor, 205) son la pared que sube
NICHOS = {131, 138, 209, 214}
PUERTAS_SECRETAS = SECRETAS - NICHOS
BARRILES = {179}                     # barril (clase Hider): en el 4, el barril que se rompe a golpes (def 2)


def _secciones(db):
    out = []
    p = 0
    for _ in range(4):
        if p + 4 > len(db):
            out.append(b"")
            continue
        n = struct.unpack_from("<I", db, p)[0]
        out.append(db[p + 4:p + 4 + n])
        p += 4 + n
    return out


def leer(fdat, nivel):
    """(enemigos, objetos) del nivel. enemigo: dict(modelo, x, y, capa, fx, fy, fz, giro);
    objeto: dict(id, x, y, capa, fx, fy, fz, giro, param)."""
    clases, ents, objs, _ = _secciones(fdat[3 * nivel + 1])
    # las clases son de 120 bytes en la versión europea (122 en otras): se mira cuál deja modelos coherentes
    paso = 120
    for p in (120, 122, 124):
        if len(clases) >= p * 2 and clases[p] != 0xFF and clases[p + 1] in (4, 0x40, 40):
            paso = p
            break
    modelo_clase = [clases[i * paso] if i * paso < len(clases) else 255 for i in range(40)]
    enemigos = []
    for i in range(len(ents) // 16):
        r = ents[i * 16:i * 16 + 16]
        modo, clase, _, x, y, _, _, capa = r[:8]
        if clase >= 40 or modo == 0xFF or x >= 80 or y >= 80:
            continue
        giro, fx, fy, fz = struct.unpack_from("<Hhhh", r, 8)
        o = clase * paso
        vida = struct.unpack_from("<H", clases, o + 26)[0] if o + 28 <= len(clases) else 0
        escala = struct.unpack_from("<H", clases, o + 50)[0] if o + 52 <= len(clases) else 4096
        enemigos.append({"modelo": modelo_clase[clase], "x": x, "y": y, "capa": capa & 1,
                         "fx": fx, "fy": fy, "fz": fz, "giro": giro, "clase": clase,
                         "vida": vida, "escala": escala})
    objetos = []
    for i in range(len(objs) // 24):
        r = objs[i * 24:i * 24 + 24]
        capa, x, y = r[0], r[1], r[2]
        oid, giro, fx, fy, fz = struct.unpack_from("<HHhhh", r, 4)
        if oid in (0xFF, 0xFFFF) or x >= 80 or y >= 80:
            continue
        objetos.append({"id": oid, "x": x, "y": y, "capa": capa & 1, "fx": fx, "fy": fy, "fz": fz,
                        "giro": giro, "param": bytes(r[14:24])})
    return enemigos, objetos


def _giro(g):
    """Giro del King's Field (0..4095) a radianes del editor. Va media vuelta desfasado: sin ella el Kraken miraba
    al túnel en vez de al agua (igual que el decorado, kf_malla._piezas)."""
    return round((g / 4096 * 2 * math.pi + math.pi) % (2 * math.pi), 3)


def _fino(f):
    """Posición fina dentro de la casilla: 0..2047 (algunos la guardan fuera: se recorta)."""
    return min(max(f, 0), 2047) / 2048.0


# Reparto a mano por nivel (lo que pidió el jugador para cada nivel, con los modelos del 4 que él eligió):
#   en el agua siempre el pez; para el resto, clase del King's Field -> registro del 4 (lista = se van turnando)
REPARTO = {
    0: {
        "agua": 26,                      # pez (copia del Seafang, chr/c0043): kf4_valle.PEZ
        "agua_modelos": {2, 5},          # Sigill y el pez largo (el 5): bajo el agua (el Baltail vuela por encima)
        "agua_por_modelo": {2: 26, 5: 100},   # con su modelo del King's Field (kf4_portar)
        "vuelan": {96},                  # el Baltail: a media altura
        0: [94],                         # Green Slime -> la babosa verde del King's Field (kf4_portar)
        14: [95],                        # Head Eater -> el del King's Field (sobre la planta c0004)
        "pulpo_lado": (-1, 0),           # el pasillo por el que llegas a la pared (el otro es el escondido)
        # Kraken: el grande (clase con 1500 de vida, escala 1) es el pulpo; los de escala 0,375, los pulpitos
        29: "kraken", "pulpo": 48, "pulpito": 65, "pulpo_vida": 1000,
        "pulpitos_max": 6, "pulpito_resto": [95, 95, 94],   # 6 pulpitos; los otros, Head Eater y alguna babosa
        21: [77],                        # Skeleton -> el esqueleto del King's Field (kf4_esqueleto, registro 77 nuevo)
        16: [63],                        # el caracol gigante, en su sitio (lo que antes eran murciélagos)
        4: [96],                         # Baltail -> el del King's Field (vuela como el murciélago)
        2: [95],                         # Sigill de tierra (los pocos fuera del agua) -> Head Eater
        "grupo": (10, 87, 15.0),         # donde hay varios murciélagos (a menos de 15 m) va una seta (c0087)
    },
}


def _cargar_cambios():
    """reparto_nivelN.json (junto a las herramientas): lo que el jugador marcó en el mapa de enemigos:
    {"cambios": {"índice del enemigo del King's Field": "chr:N" | "ninguno"}, "pulpo": [x, y]}."""
    import json
    import os
    aqui = os.path.dirname(os.path.abspath(__file__))
    for nivel, R in REPARTO.items():
        ruta = os.path.join(aqui, f"reparto_nivel{nivel}.json")
        if not os.path.isfile(ruta):
            continue
        try:
            datos = json.load(open(ruta, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        R["cambios"] = {int(k): v for k, v in datos.get("cambios", {}).items()}
        if datos.get("pulpo"):
            R["pulpo_en"] = tuple(datos["pulpo"])
        R["nuevos"] = [n for n in datos.get("nuevos", []) if n.get("tipo") and n.get("x") is not None]


_cargar_cambios()


def para_editor(fdat, nivel, pad, ox, oy, celda, altura_capa=None, vecinos=None, techo_de=None, es_agua=None):
    """Listas 'enemigos', 'items' y 'kf_objetos' (cofres, puertas, paredes que se abren) del JSON del editor,
    y un resumen.
    altura_capa(columna, fila, capa) -> metros o None: la altura del suelo de esa capa (puentes, pisos altos).
    vecinos(columna, fila) -> {(dc, df): se anda}: para girar puertas y cofres según el pasillo.
    techo_de(columna, fila) -> metros libres hasta el techo, o None."""
    enemigos, objetos = leer(fdat, nivel)

    # la casilla "X" del archivo es la fila de la rejilla y la "Y" la columna (comprobado: así caen todos
    # los enemigos sobre suelo)
    def pos(e):
        X = ox + (e["y"] + pad + _fino(e["fy"])) * celda
        Y = oy + (e["x"] + pad + _fino(e["fx"])) * celda
        return round(X, 3), round(Y, 3)

    reparto = REPARTO.get(nivel) if es_agua else None
    if reparto:
        return _para_editor_reparto(enemigos, objetos, reparto, nivel, pad, ox, oy, celda, altura_capa, vecinos,
                                    techo_de, es_agua, pos)
    # tipos: los MAX_TIPOS registros más repetidos; el resto pasa al de vida más parecida
    cuenta = collections.Counter(ENEMIGOS[e["modelo"]][1] for e in enemigos if e["modelo"] in ENEMIGOS)
    elegidos = [r for r, _ in cuenta.most_common(MAX_TIPOS)]
    if 48 in cuenta and 48 not in elegidos:      # el pulpo siempre (es uno solo y guarda la puerta)
        elegidos[-1] = 48
    cambio = {}
    for r in cuenta:
        if r not in elegidos:
            cambio[r] = min(elegidos, key=lambda c: abs(VIDA.get(c, 500) - VIDA.get(r, 500)))
    sin = collections.Counter()
    lista = []
    for e in enemigos:
        if e["modelo"] not in ENEMIGOS:
            sin[e["modelo"]] += 1
            continue
        nombre, reg, vuela = ENEMIGOS[e["modelo"]]
        reg = cambio.get(reg, reg)
        if reg in JEFES:
            reg = 24
        X, Y = pos(e)
        d = {"tipo": f"chr:{reg}", "x": X, "y": Y, "kf": nombre, "giro": _giro(e["giro"])}
        if vuela:
            d["vuela"] = True
        if altura_capa:
            z = altura_capa(e["y"], e["x"], e["capa"])
            if z is not None:
                d["z"] = round(z, 3)
        lista.append(d)
    if len(lista) > MAX_ENEMIGOS:        # repartidos por todo el nivel, no solo los primeros de la lista
        lista = [lista[i * len(lista) // MAX_ENEMIGOS] for i in range(MAX_ENEMIGOS)]
    return _resto(lista, sin, cuenta, cambio, elegidos, objetos, altura_capa, vecinos, techo_de, pos)


def _para_editor_reparto(enemigos, objetos, R, nivel, pad, ox, oy, celda, altura_capa, vecinos, techo_de, es_agua,
                         pos):
    """Los enemigos de un nivel con reparto a mano (REPARTO)."""
    secretas = [o for o in objetos if o["id"] in PUERTAS_SECRETAS]
    candidatos = [i for i, e in enumerate(enemigos) if e["modelo"] == 29 and not es_agua(e["y"], e["x"])]
    pulpo = None          # (x, y, z) donde va: delante de la pared secreta más cercana a algún Kraken
    if candidatos and secretas and R.get("pulpo") and vecinos and R.get(29) != "kraken":
        def d2(o, e):
            (a, b), (c, d) = pos(o), pos(e)
            return math.hypot(a - c, b - d)
        pared = min(secretas, key=lambda o: min(d2(o, enemigos[i]) for i in candidatos))
        col, fila = pared["y"], pared["x"]

        def alcance(c0, f0, prohibida, tope=80):
            vistas, cola = {(c0, f0)}, [(c0, f0)]
            while cola and len(vistas) < tope:
                c, f = cola.pop(0)
                for (dc, df), ok in vecinos(c, f).items():
                    q = (c + dc, f + df)
                    if ok and q not in vistas and q != prohibida:
                        vistas.add(q)
                        cola.append(q)
            return len(vistas)
        lados = [(dc, df) for (dc, df), ok in vecinos(col, fila).items() if ok]
        if lados:
            if R.get("pulpo_lado") in lados:
                dc, df = R["pulpo_lado"]
            else:
                dc, df = max(lados, key=lambda d: alcance(col + d[0], fila + d[1], (col, fila)))
            # a dos casillas de la pared, por el lado de fuera (el que da a más sitio: el escondido es el pequeño)
            c2, f2 = col + 2 * dc, fila + 2 * df
            if not vecinos(c2 - dc, f2 - df).get((dc, df)):
                c2, f2 = col + dc, fila + df
            X = ox + (c2 + pad + 0.5) * celda
            Y = oy + (f2 + pad + 0.5) * celda
            z = altura_capa(c2, f2, pared.get("capa", 0)) if altura_capa else None
            giro = math.atan2(-dc, -df)            # mirando a la pared
            pulpo = (round(X, 3), round(Y, 3), z, round(giro, 3))
    turno = collections.Counter()
    sin = collections.Counter()
    lista = []
    slime_raro = False
    for i, e in enumerate(enemigos):
        m = e["modelo"]
        nombre = ENEMIGOS.get(m, (f"modelo {m}",))[0]
        agua = es_agua(e["y"], e["x"])
        if agua and m in R["agua_modelos"]:
            reg = R.get("agua_por_modelo", {}).get(m, R["agua"])
        elif R.get(m) == "kraken":
            reg = R["pulpo"] if e.get("vida", 0) >= R["pulpo_vida"] else R["pulpito"]
        elif m in R and isinstance(R[m], list):
            regs = R[m]
            reg = regs[turno[m] % len(regs)]
            turno[m] += 1
            if m == 0 and not slime_raro and turno[m] == 4 and R.get("slime_raro"):
                reg, slime_raro = R["slime_raro"], True
        else:
            sin[m] += 1
            continue
        cambio = R.get("cambios", {}).get(i)           # lo que el jugador eligió en el mapa (reparto_nivel0.json)
        if cambio == "ninguno":
            continue
        if cambio:
            reg = int(cambio[4:])
        X, Y = pos(e)
        d = {"tipo": f"chr:{reg}", "x": X, "y": Y, "kf": nombre, "giro": _giro(e["giro"]), "i": i}
        if reg in R.get("vuelan", ()):
            d["vuela"] = True
        if agua and reg in R.get("agua_por_modelo", {}).values() or agua and reg == R["agua"]:
            d["agua"] = True                 # kf4_editor lo pone bajo la superficie del agua
        elif agua:
            d["sobre_agua"] = True           # los que no nadan (el Baltail): por encima del agua
        elif altura_capa:
            z = altura_capa(e["y"], e["x"], e["capa"])
            if z is not None:
                d["z"] = round(z, 3)
        lista.append(d)
    if pulpo:
        d = {"tipo": f"chr:{R['pulpo']}", "x": pulpo[0], "y": pulpo[1], "kf": "Kraken", "giro": pulpo[3]}
        if pulpo[2] is not None:
            d["z"] = round(pulpo[2], 3)
        lista.append(d)
    if R.get("pulpo_en"):                         # el sitio del pulpo que eligió el jugador (x, y del editor)
        lista = [d for d in lista if d["tipo"] != f"chr:{R['pulpo']}"]
        X, Y = R["pulpo_en"]
        d = {"tipo": f"chr:{R['pulpo']}", "x": round(X, 3), "y": round(Y, 3), "kf": "Kraken", "giro": 0.0}
        if altura_capa:
            col_ = int(round((X - ox) / celda - pad - 0.5))
            fila_ = int(round((Y - oy) / celda - pad - 0.5))
            z = altura_capa(col_, fila_, 0)
            if z is not None:
                d["z"] = round(z, 3)
        lista.append(d)
    for n in R.get("nuevos", []):                # enemigos añadidos en el mapa (donde el original no tenía)
        X, Y = float(n["x"]), float(n["y"])
        d = {"tipo": n["tipo"], "x": round(X, 3), "y": round(Y, 3), "kf": "añadido", "giro": 0.0}
        if altura_capa:
            col_ = int(math.floor((X - ox) / celda - pad))
            fila_ = int(math.floor((Y - oy) / celda - pad))
            z = altura_capa(col_, fila_, int(n.get("capa", 0)))
            if z is not None:
                d["z"] = round(z, 3)
        lista.append(d)
    # pulpitos: el original pone 20 en el nivel 0 y salían casi todos los enemigos pulpitos. Se quedan
    # R["pulpitos_max"], repartidos (cada uno el más lejos de los ya puestos y del grande); los demás, R["pulpito_resto"]
    if R.get("pulpitos_max") is not None:
        mini = f"chr:{R['pulpito']}"
        cand = [d for d in lista if d["tipo"] == mini]
        puestos = [(d["x"], d["y"]) for d in lista if d["tipo"] == f"chr:{R['pulpo']}"]
        quedan = []
        while cand and len(quedan) < R["pulpitos_max"]:
            d = max(cand, key=lambda d: min(((d["x"] - x) ** 2 + (d["y"] - y) ** 2 for x, y in puestos),
                                            default=0.0))
            cand.remove(d)
            quedan.append(d)
            puestos.append((d["x"], d["y"]))
        resto = R.get("pulpito_resto", [4])
        for k, d in enumerate(cand):
            d["tipo"] = f"chr:{resto[k % len(resto)]}"
    murc, seta, radio = R["grupo"]
    hechos = []
    for d in lista:
        if "i" in d and d["i"] in R.get("cambios", {}):
            continue                              # elegido a mano: no se toca
        if d["tipo"] != f"chr:{murc}":
            continue
        cerca = [o for o in lista if o is not d and o["tipo"] == f"chr:{murc}"
                 and math.hypot(o["x"] - d["x"], o["y"] - d["y"]) < radio]
        if len(cerca) >= 1 and all(math.hypot(h["x"] - d["x"], h["y"] - d["y"]) >= radio for h in hechos):
            d["tipo"] = f"chr:{seta}"
            hechos.append(d)
    cuenta = collections.Counter(int(d["tipo"][4:]) for d in lista)
    return _resto(lista, sin, cuenta, {}, sorted(cuenta), objetos, altura_capa, vecinos, techo_de, pos)


def _resto(lista, sin, cuenta, cambio, elegidos, objetos, altura_capa, vecinos, techo_de, pos):
    items, cofres, puertas, secretas = [], [], [], []
    en_cofre = {(o["x"], o["y"]) for o in objetos if o["id"] in COFRES or o["id"] in BARRILES}
    contenido = {}                       # casilla del cofre -> objeto del 4 que hay dentro
    for o in objetos:
        if o["id"] in OBJETOS and (o["x"], o["y"]) in en_cofre:
            contenido.setdefault((o["x"], o["y"]), OBJETOS[o["id"]])
    puestas = set()
    for o in objetos:
        X, Y = pos(o)
        col, fila = o["y"], o["x"]
        z = altura_capa(col, fila, o["capa"]) if altura_capa else None
        oid = o["id"]
        if oid in OBJETOS:
            if (o["x"], o["y"]) in en_cofre:
                continue                    # va dentro del cofre
            it = {"id": OBJETOS[oid], "x": X, "y": Y, "kf": oid}
            if z is not None:
                it["z"] = round(z, 3)
            items.append(it)
            continue
        if oid in GUARDADOS:
            # el cristal de guardar del King's Field (en la pared): la piedra de guardado del IV en el suelo,
            # delante de la pared y mirando al paso (su modelo mira a -z, con la media vuelta del decorado)
            a = o["giro"] / 4096 * 2 * math.pi + math.pi
            fx, fy = -math.sin(a), -math.cos(a)
            d = {"tipo": "guardado", "x": round(X + fx * GUARDADO_DELANTE, 3), "y": round(Y + fy * GUARDADO_DELANTE, 3),
                 "kf": oid, "giro": round(math.atan2(fx, fy) + math.pi, 4)}   # (la piedra del IV mira al revés que el cofre: +180)
            if z is not None:
                d["z"] = round(z, 3)
            cofres.append(d)
            continue
        if oid not in (121, 123) and oid not in PUERTAS and oid not in PUERTAS_SECRETAS and oid not in BARRILES:
            continue
        if (col, fila) in puestas:          # puertas de dos hojas: una por casilla
            continue
        puestas.add((col, fila))
        v = vecinos(col, fila) if vecinos else {}
        techo = techo_de(col, fila) if techo_de else None
        ew = v.get((1, 0)) and v.get((-1, 0))
        ns = v.get((0, 1)) and v.get((0, -1))
        if ew and not ns:
            giro = math.pi / 2              # el paso va de este a oeste: la hoja cruza en norte-sur
        elif ns and not ew:
            giro = 0.0
        else:
            giro = 0.0 if (o["giro"] // 1024) % 2 == 0 else math.pi / 2
        if z is None and altura_capa:
            # la casilla de una puerta o pared secreta no tiene suelo (es el hueco de la pared): la altura del
            # paso que cierra, el suelo de las casillas de al lado (la más baja). Sin esto la losa quedaba a la
            # altura de la rejilla (lo alto de la roca) y no se veía: solo el hueco
            vecinas = [altura_capa(col + dc, fila + dr, c) for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1))
                       for c in (o["capa"], 1 - o["capa"])]
            vecinas = [h for h in vecinas if h is not None]
            if vecinas:
                z = min(vecinas)
        d = {"x": X, "y": Y, "kf": oid}
        if z is not None:
            d["z"] = round(z, 3)
        if oid in BARRILES:
            d.update(tipo="barril", giro=round(o["giro"] / 4096 * 2 * math.pi, 4), medida=[1.33, 1.56],
                     objeto=contenido.get((o["x"], o["y"]), 0))
            cofres.append(d)
        elif oid in (121, 123):
            # el cofre de espaldas a la pared que tenga; su objeto dentro
            for (dc, dr), g in (((0, -1), 0.0), ((0, 1), math.pi), ((1, 0), -math.pi / 2), ((-1, 0), math.pi / 2)):
                if v and not v.get((dc, dr), True):
                    giro = g
                    break
            d.update(tipo="cofre", giro=round(giro, 4), medida=[1.6, None], objeto=contenido.get((o["x"], o["y"]), 0))
            cofres.append(d)
        elif oid in PUERTAS:
            alto = min(3.05, techo) if techo else 3.05
            d.update(tipo="puerta", giro=round(giro, 4), medida=[CELDA_M, round(alto, 3)])
            puertas.append(d)
        else:
            alto = techo if techo else 3.0
            # la pared secreta: el giro sale de su propio modelo (130: el paso va a lo largo de su x), no de las
            # casillas de al lado (la de detrás de la pared no cuenta como paso y salía girada 90 grados: la losa
            # del IV, con su colisión, quedaba atravesada y al subir la pared seguía habiendo una pared invisible)
            giro = (o["giro"] / 4096 * 2 * math.pi + math.pi / 2) % math.pi
            d.update(tipo="secreta", giro=round(giro, 4), medida=[CELDA_M, round(alto, 3)])
            secretas.append(d)
    resumen = {
        "enemigos": collections.Counter(d["kf"] for d in lista),
        "tipos_kf4": [f"chr:{r}" for r in elegidos],
        "cambiados": cambio,
        "sin_equivalente": sin,
        "objetos": len(items), "cofres": len(cofres), "puertas": len(puertas), "secretas": len(secretas),
    }
    return lista, items, cofres + puertas + secretas, resumen
