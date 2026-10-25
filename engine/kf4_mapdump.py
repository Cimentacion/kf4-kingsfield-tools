#!/usr/bin/env python3
"""
kf4_mapdump.py - Analiza los 64 mapas de King's Field IV (PAL) a partir de la
carpeta que generó kf4_extract.py, como paso previo al generador de mapas.

Uso:
    python kf4_mapdump.py                       (usa la .iso que haya junto al script)
    python kf4_mapdump.py "King's Field IV.iso"
    python kf4_mapdump.py C:\\ruta\\kf4_extract\\files
    python kf4_mapdump.py C:\\ruta\\files --sin-ply   (no exporta geometría)
    python kf4_mapdump.py C:\\ruta\\files --solo 016,026,031   (solo esos mapas)
    python kf4_mapdump.py --volcar 016,026,031   (copia esos .map y los param en bruto a kf4_mapas/raw)

Genera kf4_mapas/ junto al script:
    resumen.csv       un mapa por fila: nombre, orden de la guía, tamaños, recuentos, niebla, inicio
    vecinos.csv       el grafo del mundo: qué mapa enlaza con cuál (tabla de vecinos de cada mapa)
    enemigos.csv      cada spawn: mapa, registro chr.prm, tipo, familia, vida, exp, modo, radio
    objetos.csv       cada objeto de mapa: clase (obj.prm), tipo, objeto que da (cofres, huesos, barriles)
    items_suelo.csv   objetos tirados en el suelo, con probabilidad de aparecer
    piezas.csv        catálogo de piezas de geometría (OMD): tamaño, triángulos, texturas, usos
    registros.csv     cada colocación de pieza: transformación, niebla, luz, bloque de flags, vecino
    progresion.txt    el juego en el orden de la guía: enemigos nuevos, armas, armaduras, objetos
    log.txt           comprobaciones de coherencia y errores
    json/NNN.json     todo lo anterior por mapa, para el generador
    ply/NNN.ply       geometría del mapa con vertex colors y UV (Blender 2.79: File > Import > PLY)

Formatos según la decompilación kfiv-decomp (SLUS-20318) y ToolsForKFIV.
Los campos marcados (?) son deducidos, no confirmados. Solo librería estándar (Python 3.8+).
"""

import os
import sys
import csv
import json
import math
import glob
import re
import struct
import traceback

# ======================= Tablas conocidas =======================
# Mapa -> (orden en la guía Prima, nombre). Fuente: kfiv-decomp/docs/GAME_DATA.md
MAPAS = {
    0: (2, "Village Ruins"), 2: (6, "Miner's Cemetery"), 4: (3, "East Valley"),
    5: (9, "Catacombs (Giant Spider's Lair)"), 6: (23, "King's Throne, Upper"),
    7: (24, "King's Throne, Lower"), 8: (7, "Upper Mines"), 9: (8, "Lower Mines"),
    11: (14, "The Armory"), 12: (13, "Ancient City Exterior"), 13: (21, "Holy Forest"),
    14: (22, "Heart of the Forest"), 15: (15, "Ancient City L3 West"), 16: (27, "South Cliffs"),
    17: (29, "The Forge (017)"), 18: (29, "The Forge (018)"), 19: (29, "The Forge (019)"),
    20: (28, "Earth Folks' Village"), 21: (43, "Ocean Fortress"), 22: (45, "Queen's Palace"),
    23: (47, "Widda Queen's Lair"), 24: (30, "Cavern of Lava"), 25: (31, "Fire Lord's Domain"),
    26: (41, "Cliff Passage"), 27: (42, "Ocean Shore"), 28: (44, "Seabed Cave"),
    29: (26, "Underground Canal"), 30: (57, "Passage of Light"), 31: (18, "North Cliffs"),
    32: (48, "Egg Mines"), 33: (54, "Mansion of Howling Winds, Exterior"),
    34: (55, "Mansion of Howling Winds, Interior"), 35: (59, "Guardian's Room"),
    36: (61, "Underground Jail"), 37: (60, "Old Battlefield"), 38: (62, "Dark Sanctuary"),
    39: (63, "Dark Reality, Entrance"), 40: (64, "Dark Reality, Conclusion"),
    41: (25, "King's Throne, Alcoves"), 42: (58, "Sanctuary of Light"),
    43: (46, "Queen's Palace, Catacombs"), 44: (49, "Snake Dens"),
    95: (10, "Underground Graveyard (Upper/Lower)"), 96: (5, "The Shop"),
    97: (12, "Icon of Healing"), 98: (4, "Palace of Oath Interior"), 99: (1, "Palace of Oath Exterior"),
    100: (16, "Ancient City L3 Central Tower"), 101: (17, "Ancient City L3 North"),
    102: (19, "Ancient City L3 East"), 103: (20, "Ancient City L3 East Catacombs"),
    104: (35, "Ancient City L3 South, Craftsman's Room"), 105: (32, "Ancient City L3 South"),
    106: (33, "Ancient City L3 South, Widda Areas"), 107: (37, "Ancient City L2 Central Tower"),
    108: (36, "Ancient City L2 South"), 109: (38, "Ancient City L2 West"),
    110: (39, "Ancient City L2 West, Sorcerer's Area"), 111: (40, "Ancient City L2 North"),
    112: (52, "Ancient City L1 Central Tower"), 113: (50, "Ancient City L1 West"),
    114: (51, "Ruins of the Dark Folk"), 115: (53, "Ancient City L1 and L2 East"),
    116: (56, "The Treasury"),
}

# Tipo de entidad (chr.prm byte 0x02) -> familia. Fuente: cabeceras de kfiv-decomp/src/game/enemy/*.c
TIPOS = {
    1: "Slime", 2: "Reaper", 3: "Spider", 4: "Giant Spider", 5: "Beetle", 6: "Skeleton Soldier",
    7: "Expedition Soldier", 8: "Stool", 9: "Skeleton Archer", 10: "Blood Bat", 11: "Living Dead",
    12: "Crow", 13: "Expedition Archer", 14: "Phagos", 15: "NPC", 16: "Scorpion", 17: "Dragon Fly",
    18: "Acid Crawler", 19: "Widda", 20: "Widda Archer", 21: "Snake", 22: "Salamander",
    23: "Stone Guardian", 24: "Fire Lord", 25: "Critter", 26: "Slasher", 28: "Seafang",
    29: "Golden Statue", 30: "Widdacona", 31: "Eye Pedestal (atrezo)", 32: "Lava Face",
    33: "Sentinel", 34: "Lava Lizard", 35: "Giant", 36: "Living Armor", 37: "Hammer Skeleton (atrezo)",
    38: "Bell (atrezo)", 39: "Mummy", 40: "Zombie", 41: "Malformed Giant", 42: "Ancient Mummy",
    43: "Para Stool", 44: "Dark Soldier", 45: "Earth King", 46: "Widda Queen", 47: "Ice Golem",
    48: "Fire Elemental", 49: "Earth Elemental", 50: "Wind Elemental", 51: "Water Elemental",
    52: "Dark Puppet", 53: "Dark Sorcerer", 54: "Dark Succubus", 55: "Dark Archer",
    56: "Greater Demon", 57: "Aqualizard", 58: "Malice", 59: "Dark Bird", 60: "Minion",
    61: "Ancient King", 62: "High Skeleton", 63: "Giant Leader", 64: "Dark Knight", 65: "Skull",
    66: "Fire Genie", 67: "Larva", 68: "Lava Bird", 69: "Mutant Ceiling", 70: "Mutant Wall",
    71: "Dark Flower", 73: "Watcher", 74: "Onyx", 75: "Dark One (jefe final)", 76: "Giant Beetle",
    77: "Forest Golem", 78: "Makara", 79: "Master Fadin", 80: "Fadin", 81: "Perro (NPC)",
    82: "Living Statue",
}

# Clase de objeto de mapa (obj.prm byte 0x00). Fuente: map_object.h y GAME_DATA.md
CLASES_OBJ = {
    0: "decorado/ambiente", 1: "puerta", 2: "puerta doble", 3: "huesos/tumba con objeto",
    4: "cofre", 5: "se desvanece con la distancia", 6: "puerta móvil", 7: "palanca (?)",
    8: "interruptor", 9: "luz", 12: "símbolo de paso (varitas)", 17: "puerta de señal",
    18: "trampilla", 20: "punto de guardado", 21: "barril/vasija/caja",
}

ACC = {0xA7: "á", 0xB0: "í", 0xB4: "ñ", 0xB5: "ó", 0xB9: "ú", 0x0E: ".", 0x0D: "-"}

# Desplazamientos fijos de la cabecera de mapa (MapSlotUnk08 en map.h)
OFF_FOG = 0x80          # 32 bloques de niebla de 0x20
OFF_LIGHT = 0x480       # 32 bloques de luz de 0x80
OFF_SCROLL = 0x1480     # texturas animadas (0x340)
OFF_RECORDS = 0x17C0    # registros de pieza de 0x80
REC = 0x80
FLAGBLK = 0x40
NEIGH = 0x10
NEIGH_N = 32
OBJREC = 0x80
SPAWNREC = 0x60
ITEMREC = 0x40


# ======================= Utilidades =======================
def kf_text(b):
    out = []
    for i in range(0, len(b) - 1, 2):
        c, h = b[i], b[i + 1]
        if c == 0xFF and h == 0xFF:
            break
        if h != 0x08:
            break
        if c == 0:
            out.append(" ")
        elif 0x21 <= c <= 0x3A or 0x41 <= c <= 0x5A or 0x10 <= c <= 0x19:
            out.append(chr(c + 0x20))
        else:
            out.append(ACC.get(c, f"[{c:02X}]"))
    return "".join(out).strip()


def item_cat(i):
    for lo, hi, name in ((0, 150, "objeto"), (150, 220, "arma"), (220, 250, "escudo"),
                         (250, 275, "casco"), (275, 300, "armadura"), (300, 325, "guanteletes"),
                         (325, 350, "botas"), (350, 360, "anillo"), (360, 370, "brazalete"),
                         (370, 380, "amuleto")):
        if lo <= i < hi:
            return name
    return "?"


def u8(b, o):
    return b[o]


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def s16(b, o):
    return struct.unpack_from("<h", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def f32(b, o, n=1):
    v = struct.unpack_from(f"<{n}f", b, o)
    return v[0] if n == 1 else list(v)


def rnd(v, k=2):
    if isinstance(v, (list, tuple)):
        return [round(x, k) if math.isfinite(x) else None for x in v]
    return round(v, k) if math.isfinite(v) else None


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        w.writerows(rows)


# ======================= Matrices (convención de ToolsForKFIV) =======================
def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def mat_trs(pos, rot, scl):
    """Fila-vector: v * Rx * Ry * Rz * S * T, igual que SceneNodeStaticMesh.cs."""
    cx, sx = math.cos(rot[0]), math.sin(rot[0])
    cy, sy = math.cos(rot[1]), math.sin(rot[1])
    cz, sz = math.cos(rot[2]), math.sin(rot[2])
    rx = [[1, 0, 0, 0], [0, cx, sx, 0], [0, -sx, cx, 0], [0, 0, 0, 1]]
    ry = [[cy, 0, -sy, 0], [0, 1, 0, 0], [sy, 0, cy, 0], [0, 0, 0, 1]]
    rz = [[cz, sz, 0, 0], [-sz, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    s = [[scl[0], 0, 0, 0], [0, scl[1], 0, 0], [0, 0, scl[2], 0], [0, 0, 0, 1]]
    t = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [pos[0], pos[1], pos[2], 1]]
    return mat_mul(mat_mul(mat_mul(mat_mul(rx, ry), rz), s), t)


def mat_apply(m, v):
    x, y, z = v
    return (x * m[0][0] + y * m[1][0] + z * m[2][0] + m[3][0],
            x * m[0][1] + y * m[1][1] + z * m[2][1] + m[3][1],
            x * m[0][2] + y * m[1][2] + z * m[2][2] + m[3][2])


def to_gl_trs(pos, rot, scl):
    """Del espacio PS2 (Y hacia abajo) al espacio GL que usa ToolsForKFIV."""
    tau = 6.28318530718
    return ((pos[0], -pos[1], -pos[2]), (rot[0], tau - rot[1], tau - rot[2]),
            (scl[0] if scl[0] else 1.0, scl[1] if scl[1] else 1.0, scl[2] if scl[2] else 1.0))


# ======================= OMD (geometría) =======================
def tex0_decode(v):
    return {
        "TBP": v & 0x3FFF, "TBW": (v >> 14) & 0x3F, "PSM": (v >> 20) & 0x3F,
        "TW": (v >> 26) & 0xF, "TH": (v >> 30) & 0xF, "TCC": (v >> 34) & 1,
        "TFX": (v >> 35) & 3, "CBP": (v >> 37) & 0x3FFF, "CPSM": (v >> 51) & 0xF,
    }


PSM_NAME = {0: "32", 1: "24", 2: "16", 0x13: "8bpp", 0x14: "4bpp", 0x0A: "16S"}


def parse_omd(d, base, want_geom, log, tag):
    """Devuelve info del OMD y, si want_geom, la lista de triángulos en espacio GL local."""
    length = u32(d, base)
    nmesh = u16(d, base + 4)
    ntri = u16(d, base + 6)
    nvert = u32(d, base + 8)
    info = {"offset": base, "length": length, "meshes": nmesh, "tris_cabecera": ntri,
            "verts_cabecera": nvert, "tris": 0, "texturas": set(), "min": [1e9] * 3, "max": [-1e9] * 3,
            "packets": 0, "packet_qw_mismatch": 0}
    tris = []
    if length <= 0 or base + length > len(d) or nmesh > 512:
        raise ValueError(f"OMD inválido en 0x{base:X}: length={length} meshes={nmesh}")
    for mi in range(nmesh):
        mo = base + 0x10 + mi * 48
        mt = f32(d, mo, 3)
        mr = f32(d, mo + 12, 3)
        ms = f32(d, mo + 24, 3)
        off_ts, n_ts = u32(d, mo + 36), u32(d, mo + 40)
        p, r, s = to_gl_trs(mt, mr, ms)
        mmat = mat_trs(p, r, s)
        pos = base + off_ts
        for _ in range(n_ts):
            if pos + 0x90 > len(d):
                log.append(f"{tag}: paquete fuera del archivo en 0x{pos:X}")
                break
            qw = u32(d, pos)
            tex0 = struct.unpack_from("<Q", d, pos + 0x40)[0]
            nv = d[pos + 0x70]
            vstart = pos + 0x90
            step = 0x90 + nv * 32 + 16
            if qw and qw * 16 != step:
                info["packet_qw_mismatch"] += 1
            t = tex0_decode(tex0)
            info["texturas"].add((t["TBP"], t["CBP"], t["PSM"], 1 << t["TW"], 1 << t["TH"]))
            info["packets"] += 1
            verts = []
            for k in range(nv):
                vo = vstart + k * 32
                px, py, pz, _pw, nx, ny, nz, nw, tu, tv, _a, _b, cr, cg, cb, ca = struct.unpack_from(
                    "<4h4h4h4H", d, vo)
                g = mat_apply(mmat, (px, -py, -pz))
                for a in range(3):
                    info["min"][a] = min(info["min"][a], g[a])
                    info["max"][a] = max(info["max"][a], g[a])
                verts.append((g, (tu / 4096.0, tv / 4096.0), (cr, cg, cb, ca), nw))
            for i in range(nv - 2):
                if verts[i + 2][3] == -32768:   # bit ADC: no se dibuja este triángulo
                    continue
                a, b, c = (verts[i], verts[i + 1], verts[i + 2]) if i % 2 == 0 else \
                    (verts[i + 1], verts[i], verts[i + 2])
                info["tris"] += 1
                if want_geom:
                    tris.append((a[:3], b[:3], c[:3], t["TBP"], t["CBP"]))
            pos += step
    info["texturas"] = sorted(info["texturas"])
    return info, tris


def walk_omds(d, start, count, want_geom, log, tag):
    out, pos = [], start
    for i in range(count):
        try:
            info, tris = parse_omd(d, pos, want_geom, log, f"{tag} OMD {i}")
        except Exception as e:  # noqa
            log.append(f"{tag}: OMD {i} en 0x{pos:X} no se pudo leer: {e}")
            break
        out.append((info, tris))
        pos += info["length"]
    return out


# ======================= Mapa =======================
def parse_map(d, num, chr_tab, obj_tab, item_names, want_geom, log):
    tag = f"{num:03d}.map"
    h = {
        "file_size": u32(d, 0x00), "off_record_models": u32(d, 0x04), "off_record_collision": u32(d, 0x08),
        "off_object_models": u32(d, 0x0C), "off_skinned_objects": u32(d, 0x10),
        "off_object_collision": u32(d, 0x14), "off_object_motion": u32(d, 0x18),
        "off_item_models": u32(d, 0x20), "off_packets_tex": u32(d, 0x24), "off_sound_bank": u32(d, 0x28),
        "n_record_models": u16(d, 0x2C), "n_record_collision": u16(d, 0x2E),
        "n_object_models": u16(d, 0x30), "n_skinned_objects": u16(d, 0x32),
        "n_object_collision": u16(d, 0x34), "n_object_motion": u16(d, 0x36),
        "n_item_models": u16(d, 0x3A), "n_records": u16(d, 0x3C), "n_flag_blocks": u16(d, 0x3E),
        "n_objects": u16(d, 0x40), "n_spawns": u16(d, 0x42), "n_items": u16(d, 0x44),
        "off_script": u32(d, 0x4C), "fog_rgb": [d[0x50], d[0x51], d[0x52]],
        "start": rnd(f32(d, 0x60, 4), 3), "bgm": d[0x70], "light_items": d[0x71],
        "tint_rgba": [d[0x78], d[0x79], d[0x7A], d[0x7B]],
    }
    # --- niebla y luz ---
    fog = []
    for i in range(32):
        o = OFF_FOG + i * 0x20
        fog.append({"base(?)": rnd(f32(d, o + 8), 4), "inv_depth(?)": rnd(f32(d, o + 12), 6),
                    "gs_fog_word": f"0x{struct.unpack_from('<Q', d, o + 16)[0]:016X}"})
    light = []
    for i in range(32):
        o = OFF_LIGHT + i * 0x80
        dirs = f32(d, o, 16)
        cols = f32(d, o + 0x40, 16)
        light.append({"dirs[eje][luz]": rnd(dirs, 3), "colores": rnd(cols, 3)})
    # --- registros (colocación de piezas) ---
    recs = []
    for i in range(h["n_records"]):
        o = OFF_RECORDS + i * REC
        recs.append({
            "i": i, "pos": rnd(f32(d, o, 3)), "rot": rnd(f32(d, o + 0x10, 3), 4), "scale": rnd(f32(d, o + 0x20, 3), 3),
            "omd": s16(d, o + 0x30), "csk": s16(d, o + 0x32), "fog": d[o + 0x34], "light": d[o + 0x35],
            "flag_bit": d[o + 0x38], "needs_neighbour": d[o + 0x39], "neighbour": d[o + 0x3A],
            "b3B": d[o + 0x3B], "flags": f"0x{u32(d, o + 0x3C):08X}",
            "omd_aabb": rnd(f32(d, o + 0x40, 3) + f32(d, o + 0x50, 3)),
            "csk_aabb": rnd(f32(d, o + 0x60, 3) + f32(d, o + 0x70, 3)),
        })
    pos = OFF_RECORDS + h["n_records"] * REC
    flag_blocks = [d[pos + i * FLAGBLK:pos + (i + 1) * FLAGBLK].hex() for i in range(h["n_flag_blocks"])]
    pos += h["n_flag_blocks"] * FLAGBLK
    neigh = []
    for i in range(NEIGH_N):
        o = pos + i * NEIGH
        x, y, z = f32(d, o, 3)
        m = u16(d, o + 12)
        neigh.append({"i": i, "offset": rnd([x, y, z]), "map": m, "raw_0E": u16(d, o + 14)})
    pos += NEIGH_N * NEIGH
    # --- objetos ---
    objs = []
    for i in range(h["n_objects"]):
        o = pos + i * OBJREC
        di = u16(d, o + 0x30)
        kind = obj_tab[di] if di < len(obj_tab) else -1
        p0 = s16(d, o + 0x44)
        gives = ""
        if kind in (3, 4, 21) and 0 < p0 < len(item_names):
            gives = item_names[p0] or f"objeto {p0}"
        objs.append({
            "i": i, "pos": rnd(f32(d, o, 3)), "rot": rnd(f32(d, o + 0x10, 3), 4), "scale": rnd(f32(d, o + 0x20, 3), 3),
            "def": di, "kind": kind, "kind_name": CLASES_OBJ.get(kind, "?"), "model": s16(d, o + 0x32),
            "collision": s16(d, o + 0x34), "motion": s16(d, o + 0x36),
            "spawn_flags": f"0x{struct.unpack_from('<Q', d, o + 0x38)[0]:016X}",
            "use_script": u16(d, o + 0x40), "break_script": u16(d, o + 0x42),
            "param": [s16(d, o + 0x44 + k * 2) for k in range(8)], "item": p0 if gives else None,
            "item_name": gives,
        })
    pos += h["n_objects"] * OBJREC
    # --- spawns ---
    spawns = []
    for i in range(h["n_spawns"]):
        o = pos + i * SPAWNREC
        rec = u16(d, o + 0x30)
        c = chr_tab.get(rec, {})
        spawns.append({
            "i": i, "pos": rnd(f32(d, o, 3)), "rot_y": rnd(f32(d, o + 0x14), 3), "chr": rec,
            "type": c.get("type"), "familia": TIPOS.get(c.get("type"), f"tipo {c.get('type')}"),
            "hp": c.get("hp"), "exp": c.get("exp"), "modelo_chr": c.get("model"),
            "pool": d[o + 0x34], "death_script": u16(d, o + 0x36),
            "spawn_flags": f"0x{struct.unpack_from('<Q', d, o + 0x38)[0]:016X}",
            "mode": d[o + 0x40], "variant": d[o + 0x41], "wander_radius": u16(d, o + 0x4C),
            "talk_script": u16(d, o + 0x4E), "respawn_dist": u16(d, o + 0x50), "respawn_chance": d[o + 0x52],
            "wake_dist": u16(d, o + 0x54), "item_script": u16(d, o + 0x58),
        })
    pos += h["n_spawns"] * SPAWNREC
    items = []
    for i in range(h["n_items"]):
        o = pos + i * ITEMREC
        it = u16(d, o + 0x30)
        items.append({"i": i, "pos": rnd(f32(d, o, 3)), "item": it,
                      "name": item_names[it] if it < len(item_names) else "?",
                      "cat": item_cat(it), "model": u16(d, o + 0x32), "pickup_script": u16(d, o + 0x34),
                      "required_flag": d[o + 0x36], "chance": d[o + 0x37], "group": d[o + 0x38]})
    pos += h["n_items"] * ITEMREC
    tables_end = pos

    # --- coherencia ---
    if h["off_record_models"] < tables_end:
        log.append(f"{tag}: las tablas acaban en 0x{tables_end:X} pero los modelos empiezan en "
                   f"0x{h['off_record_models']:X} (algún tamaño de registro está mal)")
    elif h["off_record_models"] - tables_end > 0x1000:
        log.append(f"{tag}: hueco de 0x{h['off_record_models'] - tables_end:X} bytes entre tablas y modelos "
                   f"(hay datos sin identificar)")
    if h["file_size"] > len(d):
        log.append(f"{tag}: cabecera dice {h['file_size']} bytes y el archivo tiene {len(d)}")

    # --- piezas ---
    omds = walk_omds(d, h["off_record_models"], h["n_record_models"], want_geom, log, tag)
    uses = {}
    for r in recs:
        uses[r["omd"]] = uses.get(r["omd"], 0) + 1
    pieces = []
    for i, (info, _t) in enumerate(omds):
        size = [rnd(info["max"][a] - info["min"][a], 1) for a in range(3)]
        pieces.append({"i": i, "offset": f"0x{info['offset']:X}", "bytes": info["length"],
                       "meshes": info["meshes"], "tris": info["tris"], "packets": info["packets"],
                       "packets_qw_raros": info["packet_qw_mismatch"], "size_xyz": size,
                       "texturas": [f"TBP{t[0]:04X}/CBP{t[1]:04X}/{PSM_NAME.get(t[2], t[2])}/{t[3]}x{t[4]}"
                                    for t in info["texturas"]],
                       "usos": uses.get(i, 0)})

    sizes_sections = {
        "tablas": tables_end, "piezas_omd": h["off_record_collision"] - h["off_record_models"],
        "colision_piezas": h["off_object_models"] - h["off_record_collision"],
        "texturas_y_paquetes": h["off_sound_bank"] - h["off_packets_tex"] if h["off_sound_bank"] > h["off_packets_tex"] else None,
    }
    m = {"map": num, "name": MAPAS.get(num, (None, "?"))[1], "guia": MAPAS.get(num, (None,))[0],
         "bytes": len(d), "header": h, "secciones": sizes_sections, "fog": fog, "light": light,
         "records": recs, "flag_blocks": flag_blocks, "neighbours": neigh, "objects": objs,
         "spawns": spawns, "items": items, "pieces": pieces}
    return m, omds, recs


def write_ply(path, omds, recs):
    """Geometría colocada en el mundo, ejes de Blender (Z arriba), con vertex colors y UV."""
    verts, faces = [], []
    for r in recs:
        if r["omd"] < 0 or r["omd"] >= len(omds):
            continue
        p, ro, s = to_gl_trs(r["pos"], r["rot"], r["scale"])
        if None in p or None in ro or None in s:
            continue
        m = mat_trs(p, ro, s)
        for tri in omds[r["omd"]][1]:
            idx = []
            for (g, uv, col) in tri[:3]:
                x, y, z = mat_apply(m, g)
                c = [min(255, int(v * 2)) for v in col]
                verts.append((x / 100.0, -z / 100.0, y / 100.0, uv[0], 1.0 - uv[1], c[0], c[1], c[2], c[3]))
                idx.append(len(verts) - 1)
            faces.append(idx)
    with open(path, "wb") as f:
        f.write((f"ply\nformat binary_little_endian 1.0\ncomment KF4 mapa (escala 1/100)\n"
                 f"element vertex {len(verts)}\nproperty float x\nproperty float y\nproperty float z\n"
                 f"property float s\nproperty float t\nproperty uchar red\nproperty uchar green\n"
                 f"property uchar blue\nproperty uchar alpha\nelement face {len(faces)}\n"
                 f"property list uchar int vertex_indices\nend_header\n").encode("ascii"))
        for v in verts:
            f.write(struct.pack("<5f4B", *v))
        for fc in faces:
            f.write(struct.pack("<B3i", 3, *fc))
    return len(faces)


# ======================= Origen: ISO o carpeta =======================
SECTOR = 2048


class Source:
    """Lee archivos internos por nombre ('param/chr.prm', '016.map') desde la ISO o desde una carpeta."""

    def __init__(self, path, lang="SPA"):
        self.path = path
        self.names = {}
        if os.path.isfile(path):
            self.kind = "ISO"
            self._from_iso(path, lang)
        elif os.path.isdir(path):
            self.kind = "carpeta"
            for dp, _, fns in os.walk(path):
                for fn in fns:
                    full = os.path.join(dp, fn)
                    rel = os.path.relpath(full, path).replace("\\", "/").lower()
                    self.names[rel] = full
                    # también por nombre corto, por si la carpeta tiene un nivel más
                    tail = "/".join(rel.split("/")[-2:]) if "/" in rel else rel
                    self.names.setdefault(tail, full)
                    self.names.setdefault(fn.lower(), full)
                    if fn.lower().startswith("param_"):          # volcados de --volcar: param_x.prm
                        self.names.setdefault("param/" + fn.lower()[6:], full)
        else:
            raise RuntimeError(f"no existe: {path}")

    def _from_iso(self, iso, lang):
        with open(iso, "rb") as f:
            f.seek(16 * SECTOR)
            pvd = f.read(SECTOR)
            if pvd[1:6] != b"CD001":
                raise RuntimeError("No es una ISO9660 válida.")
            found = {}

            def walk(lba, size, prefix):
                f.seek(lba * SECTOR)
                data = f.read(size)
                off = 0
                while off < len(data):
                    ln = data[off]
                    if ln == 0:
                        off = (off // SECTOR + 1) * SECTOR
                        continue
                    rec = data[off:off + ln]
                    off += ln
                    if len(rec) < 34:
                        continue
                    nm = rec[33:33 + rec[32]]
                    if nm in (b"\x00", b"\x01"):
                        continue
                    nm = nm.decode("ascii", "replace").split(";")[0].rstrip(".")
                    rel = f"{prefix}/{nm}" if prefix else nm
                    l2, s2 = int.from_bytes(rec[2:6], "little"), int.from_bytes(rec[10:14], "little")
                    if rec[25] & 2:
                        if prefix.count("/") < 4:
                            walk(l2, s2, rel)
                    else:
                        found[rel.upper()] = (l2 * SECTOR, s2)

            root = pvd[156:190]
            walk(int.from_bytes(root[2:6], "little"), int.from_bytes(root[10:14], "little"), "")
            self.iso_files = found
            key = f"DATA/KF4_{lang}.DAT"
            if key not in found:
                key = next((k for k in found if k.startswith("DATA/KF4_") and k.endswith(".DAT")), None)
            if not key:
                raise RuntimeError("No encuentro DATA/KF4_xxx.DAT en la ISO.")
            dat_off, _ = found[key]
            self.dat_off = dat_off
            f.seek(dat_off)
            count = u32(f.read(0x40), 4)
            table = f.read(count * 0x40)
            for i in range(count):
                r = table[i * 0x40:(i + 1) * 0x40]
                nm = r[:0x34].split(b"\x00", 1)[0].decode("ascii", "replace").replace("\\", "/").lower()
                size, _alloc, off = struct.unpack_from("<III", r, 0x34)
                self.names[nm] = (dat_off + off, size)
        self.dat = key

    def has(self, name):
        return name.lower() in self.names

    def read(self, name):
        v = self.names[name.lower()]
        if isinstance(v, str):
            with open(v, "rb") as f:
                return f.read()
        with open(self.path, "rb") as f:
            f.seek(v[0])
            return f.read(v[1])


# ======================= Principal =======================
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    want_geom = "--sin-ply" not in flags
    only = None
    for i, a in enumerate(sys.argv):
        if a == "--solo" and i + 1 < len(sys.argv):
            only = {int(x) for x in sys.argv[i + 1].split(",")}
            args = [x for x in args if x != sys.argv[i + 1]]
        if a == "--volcar" and i + 1 < len(sys.argv):
            args = [x for x in args if x != sys.argv[i + 1]]
    if args:
        src_path = os.path.abspath(args[0])
    else:
        isos = glob.glob(os.path.join(here, "*.iso"))
        isos.sort(key=lambda f: ("(" in os.path.basename(f), len(f), f))   # la ISO limpia primero
        src_path = isos[0] if isos else os.path.join(here, "kf4_extract", "files")
    try:
        src = Source(src_path)
    except Exception as e:  # noqa
        print(f"ERROR: {e}")
        sys.exit(1)
    print(f"Leyendo de: {src_path}  ({src.kind})")
    for need in ("param/chr.prm", "param/item_nam.prm", "param/obj.prm"):
        if not src.has(need):
            print(f"ERROR: no encuentro {need} en {src_path}")
            print("Archivos que sí veo (primeros 20): " + ", ".join(sorted(src.names)[:20]))
            sys.exit(1)
    out = os.path.join(here, "kf4_mapas")
    for sub in ("", "json", "ply"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
    log = []

    # --- --elf: saca el ejecutable del juego (SLES_xxx.xx) de la raíz de la ISO ---
    if "--elf" in sys.argv:
        if src.kind != "ISO":
            print("ERROR: --elf necesita la ISO")
            sys.exit(1)
        exe = next((k for k in src.iso_files if re.fullmatch(r"S[LC][EUPK][SM]_\d{3}\.\d{2}", k)), None)
        if not exe:
            print("ERROR: no encuentro el ejecutable en la ISO")
            sys.exit(1)
        off, size = src.iso_files[exe]
        with open(src_path, "rb") as f:
            f.seek(off)
            data = f.read(size)
        dest = os.path.join(here, exe)
        with open(dest, "wb") as o:
            o.write(data)
        print(f"Listo -> {dest} ({size} bytes). Súbelo.")
        return

    # --- volcado en bruto: --volcar 016,026,031 copia esos archivos tal cual a kf4_mapas/raw ---
    for i, a in enumerate(sys.argv):
        if a == "--volcar" and i + 1 < len(sys.argv):
            raw = os.path.join(out, "raw")
            os.makedirs(raw, exist_ok=True)
            wanted = [f"{int(x):03d}.map" for x in sys.argv[i + 1].split(",") if x.strip().isdigit()]
            wanted += ["param/chr.prm", "param/obj.prm", "param/item_nam.prm", "param/magic.prm",
                       "param/item_wpn.prm", "param/item_pct.prm", "param/item_cmn.prm"]
            for w in wanted:
                if src.has(w):
                    with open(os.path.join(raw, w.replace("/", "_")), "wb") as o:
                        o.write(src.read(w))
                    print(f"  volcado {w}")
                else:
                    print(f"  no existe {w}")
            print(f"\nListo -> {raw}  (comprímelo y súbelo)")
            return

    # --- parámetros ---
    nam = src.read("param/item_nam.prm")
    item_names = [kf_text(nam[i * 64:i * 64 + 46]) for i in range(len(nam) // 64)]
    ch = src.read("param/chr.prm")
    chr_tab = {}
    for i in range(len(ch) // 0x450):
        r = ch[i * 0x450:(i + 1) * 0x450]
        chr_tab[i] = {"model": u16(r, 0), "type": r[2], "hp": u16(r, 0x0A), "exp": u16(r, 0x0E),
                      "drops": [u16(r, 0x232), u16(r, 0x234)]}
    ob = src.read("param/obj.prm")
    obj_tab = [ob[i * 0x80] for i in range(len(ob) // 0x80)]

    files = sorted(n for n in src.names if re.fullmatch(r"\d{3}\.map", n))
    if only:
        files = [f for f in files if int(f[:3]) in only]
    print(f"{len(files)} mapas.")
    if not files:
        print("ERROR: no hay ningún NNN.map. Archivos que veo (primeros 30): "
              + ", ".join(sorted(src.names)[:30]))
        sys.exit(1)
    maps = []
    for name in files:
        print(f"  {name} ...")
        try:
            m, omds, recs = parse_map(src.read(name), int(name[:3]), chr_tab, obj_tab, item_names,
                                      want_geom, log)
        except Exception:
            log.append(f"{name}: ERROR\n{traceback.format_exc()}")
            continue
        maps.append(m)
        with open(os.path.join(out, "json", name[:3] + ".json"), "w", encoding="utf-8") as j:
            json.dump(m, j, ensure_ascii=False, indent=1)
        if want_geom:
            try:
                n = write_ply(os.path.join(out, "ply", name[:3] + ".ply"), omds, recs)
                m["ply_tris"] = n
            except Exception:
                log.append(f"{name}: PLY falló\n{traceback.format_exc()}")

    # --- CSV ---
    rows = []
    for m in maps:
        h = m["header"]
        rows.append([f"{m['map']:03d}", m["name"], m["guia"], m["bytes"], h["n_records"], h["n_record_models"],
                     h["n_flag_blocks"], h["n_objects"], h["n_spawns"], h["n_items"],
                     sum(1 for n in m["neighbours"] if n["map"] not in (0xFFFF,) and any(n["offset"] or [0])),
                     "%d,%d,%d" % tuple(h["fog_rgb"]), h["bgm"], *h["start"],
                     sum(pc["tris"] for pc in m["pieces"])])
    write_csv(os.path.join(out, "resumen.csv"),
              ["mapa", "nombre", "orden guía", "bytes", "registros", "piezas OMD", "bloques flags", "objetos",
               "spawns", "items suelo", "vecinos", "niebla RGB", "música", "inicio X", "inicio Y", "inicio Z",
               "rumbo", "triángulos piezas"], rows)

    rows = []
    for m in maps:
        users = {}
        for r in m["records"]:
            if r["neighbour"] != 0xFF:
                users.setdefault(r["neighbour"], []).append(r["i"])
        for n in m["neighbours"]:
            if n["i"] in users or (n["map"] != 0 and n["map"] != 0xFFFF):
                rows.append([f"{m['map']:03d}", m["name"], n["i"], n["map"],
                             MAPAS.get(n["map"], (None, "?"))[1], *(n["offset"] or ["", "", ""]),
                             len(users.get(n["i"], [])), n["raw_0E"]])
    write_csv(os.path.join(out, "vecinos.csv"),
              ["mapa", "nombre", "entrada", "mapa vecino", "nombre vecino", "dx", "dy", "dz",
               "registros que lo precargan", "raw 0x0E"], rows)

    rows = []
    for m in maps:
        for s in m["spawns"]:
            rows.append([f"{m['map']:03d}", m["name"], m["guia"], s["i"], s["chr"], s["type"], s["familia"], s["hp"],
                         s["exp"], s["modelo_chr"], s["mode"], s["variant"], s["wander_radius"],
                         s["respawn_dist"], s["respawn_chance"], s["wake_dist"], *s["pos"]])
    write_csv(os.path.join(out, "enemigos.csv"),
              ["mapa", "nombre", "orden guía", "spawn", "chr.prm", "tipo", "familia", "vida", "exp", "modelo chr",
               "modo", "variante", "radio deambular", "dist. reaparición", "% reaparición", "dist. despertar",
               "X", "Y", "Z"], rows)

    rows = []
    for m in maps:
        for o in m["objects"]:
            rows.append([f"{m['map']:03d}", m["name"], o["i"], o["def"], o["kind"], o["kind_name"], o["model"],
                         o["collision"], o["item"] if o["item"] is not None else "", o["item_name"],
                         " ".join(map(str, o["param"])), o["use_script"], *o["pos"]])
    write_csv(os.path.join(out, "objetos.csv"),
              ["mapa", "nombre", "obj", "obj.prm", "clase", "clase (nombre)", "modelo", "colisión",
               "da objeto", "nombre objeto", "parámetros", "script uso", "X", "Y", "Z"], rows)

    rows = []
    for m in maps:
        for it in m["items"]:
            rows.append([f"{m['map']:03d}", m["name"], it["item"], it["name"], it["cat"], it["chance"],
                         it["group"], it["pickup_script"], *it["pos"]])
    write_csv(os.path.join(out, "items_suelo.csv"),
              ["mapa", "nombre", "id", "objeto", "categoría", "% aparece", "grupo", "script", "X", "Y", "Z"], rows)

    rows = []
    for m in maps:
        for pc in m["pieces"]:
            rows.append([f"{m['map']:03d}", m["name"], pc["i"], pc["bytes"], pc["meshes"], pc["tris"],
                         *pc["size_xyz"], pc["usos"], len(pc["texturas"]), " ".join(pc["texturas"]),
                         pc["packets_qw_raros"]])
    write_csv(os.path.join(out, "piezas.csv"),
              ["mapa", "nombre", "pieza", "bytes", "mallas", "triángulos", "ancho X", "alto Y", "fondo Z",
               "usos", "nº texturas", "texturas (VRAM)", "paquetes raros"], rows)

    rows = []
    for m in maps:
        for r in m["records"]:
            rows.append([f"{m['map']:03d}", r["i"], r["omd"], r["csk"], *r["pos"], *r["rot"], *r["scale"],
                         r["fog"], r["light"], r["flag_bit"], r["needs_neighbour"],
                         "" if r["neighbour"] == 0xFF else r["neighbour"], r["b3B"], r["flags"]])
    write_csv(os.path.join(out, "registros.csv"),
              ["mapa", "registro", "pieza OMD", "colisión CSK", "X", "Y", "Z", "rotX", "rotY", "rotZ",
               "escX", "escY", "escZ", "niebla", "luz", "bit flags", "necesita vecino", "vecino precarga",
               "byte 0x3B", "flags"], rows)

    # --- progresión ---
    seen_fam, seen_item = set(), set()
    lines = ["=== KF4 en el orden de la guía (Prima) ===",
             "NUEVO = primera vez que aparece en la partida. Base para la curva del randomizador.\n"]
    for m in sorted(maps, key=lambda x: (x["guia"] or 999, x["map"])):
        lines.append(f"[{m['guia']:>2}] {m['map']:03d}  {m['name']}")
        fams = {}
        for s in m["spawns"]:
            if s["type"] in (15, 81):
                continue
            k = s["familia"]
            fams.setdefault(k, []).append(s)
        for k, ss in sorted(fams.items(), key=lambda kv: min(x["hp"] or 0 for x in kv[1])):
            hp = sorted({x["hp"] for x in ss if x["hp"] is not None})
            ex = sorted({x["exp"] for x in ss if x["exp"] is not None})
            new = "NUEVO " if k not in seen_fam else "      "
            seen_fam.add(k)
            lines.append(f"      {new}enemigo  {k:<28} x{len(ss):<3} vida {hp}  exp {ex}")
        loot = [(o["item"], o["item_name"], o["kind_name"]) for o in m["objects"] if o["item"] is not None]
        loot += [(it["item"], it["name"], f"suelo {it['chance']}%") for it in m["items"]]
        for iid, nm, where in sorted(loot):
            cat = item_cat(iid)
            new = "NUEVO " if iid not in seen_item else "      "
            seen_item.add(iid)
            lines.append(f"      {new}{cat:<11} {iid:>3} {nm:<30} ({where})")
        saves = sum(1 for o in m["objects"] if o["kind"] == 20)
        if saves:
            lines.append(f"      punto de guardado x{saves}")
        lines.append("")
    with open(os.path.join(out, "progresion.txt"), "w", encoding="utf-8") as o:
        o.write("\n".join(lines))

    biggest = max(maps, key=lambda x: x["bytes"]) if maps else None
    with open(os.path.join(out, "log.txt"), "w", encoding="utf-8") as o:
        if biggest:
            o.write(f"Mapa más grande: {biggest['map']:03d} ({biggest['bytes']} bytes) -> límite seguro de tamaño "
                    f"para un mapa nuevo hasta saber el tamaño real del slot de memoria.\n\n")
        o.write("\n".join(log) if log else "Sin problemas de coherencia.\n")
    print(f"\nListo -> {out}\nSúbeme: resumen.csv, vecinos.csv, enemigos.csv, objetos.csv, items_suelo.csv,"
          f" piezas.csv, progresion.txt, log.txt\ny json/016.json json/026.json json/031.json (los acantilados).")


if __name__ == "__main__":
    main()
