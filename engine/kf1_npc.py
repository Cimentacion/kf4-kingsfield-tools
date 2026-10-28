#!/usr/bin/env python3
"""
kf1_npc.py - La gente que habla del King's Field (el KF2 japonés, disco europeo) y lo que dice.

Cada nivel tiene en FDAT.T la entrada 3n+1: 40 clases de 120 bytes y, en cada clase, a partir de +0x38, dieciséis
punteros a bloques. El bloque 0 de una clase que habla empieza por 0x70 (es lo que mira el intérprete del juego) y
es su conversación: 20 bytes de cabecera y el código.

  +0x0C  u16  la primera línea en TALK0.T (cada línea, una imagen con el texto)
  +0x12  u8   lo que pasa al terminar de hablar: 0x0n tienda n (GAME.EXE: tablas de 120 bytes en 0x8006D388, una
              por tienda, 1 = lo vende), 0x10 el cerrajero, 0x20 y 0x30 otros servicios, 0xFF nada
  +0x14  el código: < 0xF0 dice la línea base + byte; F0 n fin de una visita (la próxima vez sigue tras él);
         F1 flag valor etiqueta (al principio: empezar en otra parte según la historia); F2 n etiqueta;
         F4 n código propio del nivel (misiones); F5 n las n líneas siguientes sin esperar; F8 n vuelve atrás
         (ya no tiene más que decir: repite); F9 flag valor etiqueta salto; FE fin de las condiciones; FF fin

Lo mismo que el King's Field II occidental (anatoliysolomichev/kings_field_2_re, tools/escript.py), comprobado
aquí con las conversaciones de los niveles 0 y 1: una visita por vez, y la última se repite.
"""

import struct

CLASE = 120
CLASES = 40
CONVERSACION = 0x70
LONG = {0xF0: 2, 0xF2: 2, 0xF3: 1, 0xF4: 2, 0xF5: 2, 0xF6: 1, 0xF7: 3, 0xF8: 2, 0xF9: 4, 0xFF: 1}
TIENDAS_EXE = 0x8006D388 - 0x80011000 + 0x800      # GAME.EXE (europeo): tiendas, 120 bytes cada una
CARGA_EXE = 0x80011000


def _es_linea(op):
    return op < 0xF0 or op in (0xF1, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE)


def _etiqueta(code, want):
    i = 0
    while i < len(code):
        b = code[i]
        i += 1
        if b == 0xF2:
            if i < len(code) and code[i] == want:
                return i + 1
            i += 1
        elif b == 0xFF:
            return None
    return None


def _inicio(code, pc=0):
    i = 0
    while i + 3 < len(code) and code[i] == 0xF1:
        i += 4                       # condiciones de la historia: con todo a 0 no se cumple ninguna
    if i < len(code) and code[i] == 0xFE and pc == 0:
        return i + 1
    return pc


def visitas(code, maximo=16):
    """[[línea, ...], ...]: lo que dice en la primera visita, la segunda... (la última se repite siempre)."""
    pc, retry, out = 0, 0, []
    for _ in range(maximo):
        p = _inicio(code, pc)
        if retry:
            while p < len(code) and code[p] != 0xF0:
                p += 1
            p = min(p + 2, len(code))
            retry = 0
        dice, por = [], "fin"
        for _paso in range(400):
            if not 0 <= p < len(code):
                break
            op = code[p]
            if _es_linea(op):
                if op < 0xF0:
                    dice.append(op)
                p += 1
                continue
            if op == 0xFF:
                break
            if op == 0xF0:
                retry, por = 1, "sigue"
                break
            if op == 0xF8:
                # ya no tiene más que decir: lo que repite desde ahí para siempre es otra visita (la última)
                q = p - code[p + 1] if p + 1 < len(code) else p
                bucle = []
                for _ in range(64):
                    if not 0 <= q < len(code) or code[q] in (0xFF, 0xF0, 0xF8):
                        break
                    if _es_linea(code[q]):
                        if code[q] < 0xF0:
                            bucle.append(code[q])
                        q += 1
                    else:
                        q += 4 if code[q] == 0xF9 else LONG.get(code[q], 1)
                if dice:
                    out.append(dice)
                dice = bucle
                break
            if op == 0xF9:
                p += 4                   # sin flags de la historia: nunca salta
                continue
            p += LONG.get(op, 1)
        if dice:
            out.append(dice)
        pc = p
        if por != "sigue":
            break
    return out


def hablan(fdat, nivel):
    """{clase: dict(modelo, base, servicio, visitas)} de las clases del nivel que tienen conversación."""
    raw = fdat[3 * nivel + 1]
    if len(raw) < 4 + CLASES * CLASE:
        return {}
    base = 4 + CLASES * CLASE
    out = {}
    for k in range(CLASES):
        r = raw[4 + k * CLASE:4 + (k + 1) * CLASE]
        if r[1] != 4:
            continue
        off = struct.unpack_from("<I", r, 0x38)[0]
        if off == 0xFFFFFFFF or not 0 <= base + off < len(raw) - 0x14 or raw[base + off] != CONVERSACION:
            continue
        p = base + off
        cab = raw[p:p + 0x14]
        code = raw[p + 0x14:p + 0x14 + 600]
        fin = code.find(b"\xff")
        code = code[:fin + 1] if fin >= 0 else code
        vis = visitas(code)
        if not vis:
            continue
        out[k] = {"modelo": r[0], "base": struct.unpack_from("<H", cab, 0x0C)[0], "servicio": cab[0x12],
                  "visitas": vis}
    return out


def tiendas(game_exe):
    """[[objeto del King's Field, ...], ...]: lo que vende cada tienda (índice = servicio & 0x0F)."""
    out = []
    for s in range(8):
        o = TIENDAS_EXE + s * 120
        if o + 120 > len(game_exe):
            break
        e = game_exe[o:o + 120]
        if any(b > 1 for b in e):
            break
        out.append([i for i in range(120) if e[i]])
    return out


# la gente del King's Field -> un registro de gente del IV (chr.prm, tipo 0x0F) que se le parece; el modelo y los
# movimientos son los de ese registro. modelo del King's Field (MO.T) -> registro
GENTE_KF4 = {
    67: 101,     # nivel 0: el pescador de la orilla
    66: 102,     # nivel 1: el barquero que vende equipo
    95: 105,     # el cerrajero
    70: 107,     # Nola
    83: 109,     # el gordo de las hierbas
    85: 118,     # Fai, escondido
    96: 126,     # el caballero de Verdite
    87: 104,     # el minero
}
GENTE_DEFECTO = 101


def para_editor(fdat, nivel, pad, ox, oy, celda, altura_capa=None, modelos_bichos=()):
    """Lista "npcs" del JSON del editor: dónde está cada persona que habla, hacia dónde mira, su registro del IV,
    lo que dice en cada visita (líneas de TALK0.T) y su servicio (tienda, cerrajero)."""
    import kf1_objetos
    clases = hablan(fdat, nivel)
    enemigos, _ = kf1_objetos.leer(fdat, nivel)
    out = []
    for e in enemigos:
        c = clases.get(e["clase"])
        if c is None or e["modelo"] in modelos_bichos:
            continue
        X = ox + (e["y"] + pad + kf1_objetos._fino(e["fy"])) * celda
        Y = oy + (e["x"] + pad + kf1_objetos._fino(e["fx"])) * celda
        d = {"x": round(X, 3), "y": round(Y, 3), "giro": kf1_objetos._giro(e["giro"]), "clase": e["clase"],
             "kf_modelo": c["modelo"], "registro": GENTE_KF4.get(c["modelo"], GENTE_DEFECTO), "servicio": c["servicio"],
             "visitas": [[c["base"] + op for op in v] for v in c["visitas"]]}
        if altura_capa:
            z = altura_capa(e["y"], e["x"], e["capa"])
            if z is not None:
                d["z"] = round(z, 3)
        out.append(d)
    return out
