#!/usr/bin/env python3
"""Datos de la IA propia de los bichos del King's Field (ia/kf1_ia.c) para su registro del chr.prm.

Los números salen de las acciones de cada clase del nivel 0 del King's Field (FDAT.T; docs/kf1_ia.md): pesos al
elegir (byte 2, y byte 3 si ya la estaba haciendo), distancias de "moverse" (empieza / sigue / se aparta) y, de
cada golpe, desde dónde lo elige (u16 +0x1A), hasta dónde llega (byte +0x0E x 64) y su ángulo (byte +0x10 x 16 de
4096). Unidades del King's Field: 2048 por casilla de 2,5 m (1 = 0,122 cm).

Las animaciones y la fuerza de los golpes son las del bicho del IV sobre el que va (sus huesos y movimientos), menos
en el Kraken, que trae las suyas.
"""
import math
import struct

TIPO_KF1 = 0x53            # kf4_valle.TIPO_KF1
BLOQUE = 0x3F8             # en el ataque a distancia 1 (su peso, 0x3F4, se queda a 0)
U = 2.5 * 100 / 2048       # cm por unidad del King's Field


def cm(u):
    return int(round(u * U))


def grados(b16):
    return b16 * 16 * 360.0 / 4096


def ia(r, base_tipo, quieto=(0, 0), pasear=(0, 0), moverse=0, guardia=(0, 0), guardia_u=0, empieza_u=0,
       sigue_u=0, aparta_u=0, hasta_u=0, anda=True, frames=12):
    """Pone el tipo nuevo y el bloque de la IA (distancias en unidades del King's Field)."""
    r[2] = TIPO_KF1
    k = BLOQUE
    r[0x3F4] = 0
    r[k:k + 0x18] = bytes(0x18)
    r[k] = base_tipo
    r[k + 2], r[k + 3] = quieto
    r[k + 4], r[k + 5] = pasear
    r[k + 6] = moverse
    r[k + 8], r[k + 9] = guardia
    struct.pack_into("<HHHHH", r, k + 0x0A, cm(guardia_u), cm(empieza_u), cm(sigue_u), cm(aparta_u), cm(hasta_u))
    r[k + 0x14] = frames
    r[k + 0x15] = 1 if anda else 0
    struct.pack_into("<f", r, 0x1C, math.pi)              # te ve alrededor (en el King's Field, por la distancia)
    struct.pack_into("<H", r, 0x18, max(struct.unpack_from("<H", r, 0x18)[0], cm(max(empieza_u, sigue_u))))
    for o in (0x3D8, 0x410):                              # sin ataques a distancia
        r[o] = 0


def radio(r):
    return struct.unpack_from("<H", r, 0xCC)[0] * r[0xD2] / 100.0


def golpe(r, i, peso, elige_u, llega_u, angulo_b16, fuerzas=None, ventana=None, respiro=10):
    """Golpe i (0x240 + 0x88 i): lo elige si estás a menos de elige_u del centro y delante (angulo); el golpe
    llega a llega_u del centro en ese mismo arco (nunca menos que el golpe que ya tenía el bicho del IV). Sin
    fuerzas ni ventana se quedan las del bicho del IV."""
    o = 0x240 + 0x88 * i
    if not peso:
        r[o] = 0
        return
    rad = radio(r)
    ang = grados(angulo_b16)
    # el bicho del IV puede ser más grande que el del King's Field: nunca menos alcance que el suyo
    if r[o]:
        elige_u = max(elige_u, (struct.unpack_from("<H", r, o + 6)[0] + rad + 100) / U)
        llega_u = max(llega_u, (struct.unpack_from("<H", r, o + 0x30)[0] + rad) / U)
    r[o], r[o + 1], r[o + 2] = peso, 0, respiro
    struct.pack_into("<HHf", r, o + 4, 0, max(1, round(cm(elige_u) - rad - 100)), math.radians(min(180.0, ang)))
    if fuerzas is not None:
        struct.pack_into("<9h", r, o + 0x10, *fuerzas)
    p = o + 0x30
    struct.pack_into("<HH", r, p, max(1, round(cm(llega_u) - rad)), int(round(min(180.0, ang))))
    if ventana is not None:
        struct.pack_into("<HH", r, p + 4, *ventana)


def golpes_fuera(r, desde):
    for i in range(desde, 3):
        r[0x240 + 0x88 * i] = 0


# ---------------------------------------------------------------- los bichos del nivel 0

def kraken(r):
    """Clase 0: quieto (60 / 100), moverse sin andar (100; desde 10000, sigue hasta 12000), tres latigazos."""
    ia(r, 5, quieto=(0x3C, 0x64), moverse=0x64, empieza_u=10000, sigue_u=12000, anda=False)
    golpe(r, 0, 0xA0, 5800, 0x5A * 64, 0x25, (0, 33, 0, 0, 0, 0, 0, 0, 0), (24, 30))
    golpe(r, 1, 0xA0, 5800, 0x5A * 64, 0x25, (0, 40, 0, 0, 0, 0, 0, 0, 0), (24, 30))
    golpe(r, 2, 0x78, 7800, 0x79 * 64, 0x1F, (0, 47, 21, 0, 0, 0, 0, 0, 0), (24, 30))


def pulpito(r):
    """Clase 18: quieto (70 / 100), moverse (100) y se aparta a menos de 1600 hasta 2100; latigazos 100, 100, 80."""
    ia(r, 5, quieto=(0x46, 0x64), moverse=0x64, empieza_u=10000, sigue_u=12000, aparta_u=0x0640, hasta_u=0x0834)
    golpe(r, 0, 0x64, 0x0A8C, 0x2A * 64, 0x25, (0, 12, 0, 0, 0, 0, 0, 0, 0), (24, 30))
    golpe(r, 1, 0x64, 0x0A8C, 0x2A * 64, 0x25, (0, 12, 0, 0, 0, 0, 0, 0, 0), (24, 30))
    golpe(r, 2, 0x50, 0x0D7A, 0x35 * 64, 0x1F, (0, 15, 0, 0, 0, 0, 0, 0, 0), (24, 30))


def babosa(r):
    """Clase 8 (la más repetida de las babosas del modelo 0): quieto, pasear y moverse (32 / 64), empieza a
    6000 y sigue hasta 8000, se aparta tras morder hasta 800; mordisco (40) desde 1260, llega a 1024, alrededor."""
    ia(r, 1, quieto=(0x20, 0x40), pasear=(0x20, 0x40), moverse=0x20, empieza_u=6000, sigue_u=8000,
       aparta_u=800, hasta_u=800)
    golpe(r, 0, 0x28, 0x04EC, 0x10 * 64, 0x80)
    golpes_fuera(r, 1)


def head_eater(r):
    """Clase 11 (modelo 14): quieto (50 / 100), pasear (150), moverse (150; 10000 / 12000), se aparta a menos de
    2400 hasta 4560 (muerde y se retira); dos mordiscos (100 y 80) desde 3960, llegan a 3904, 52 grados."""
    ia(r, 0, quieto=(0x32, 0x64), pasear=(0x96, 0), moverse=0x96, empieza_u=10000, sigue_u=12000,
       aparta_u=0x0960, hasta_u=0x11D0)
    golpe(r, 0, 0x64, 0x0F78, 0x3D * 64, 0x25)
    golpe(r, 1, 0x50, 0x0F78, 0x3D * 64, 0x25)
    golpes_fuera(r, 2)


def esqueleto(r):
    """Clase 15 (modelo 21): pasear (64 / 110), moverse (64; 13500 / 21500), se aparta a menos de 1700 hasta 2700,
    guardia (48 / 120) a menos de 2900 si le atacas; dos espadazos: el doble tajo (48) desde 2800 que llega a 2560 a
    35 grados, y la estocada (120), que en el King's Field se lanza desde 4500 con un paso adelante y llega a 2752 a
    25 grados (aquí sin el paso: la animación es la del soldado del IV, así que se elige desde algo más que su
    llegada)."""
    ia(r, 6, pasear=(0x40, 0x6E), moverse=0x40, guardia=(0x30, 0x78), guardia_u=0x0B54, empieza_u=0x34BC,
       sigue_u=0x53FC, aparta_u=0x06A4, hasta_u=0x0A8C)
    golpe(r, 0, 0x30, 0x0AF0, 0x28 * 64, 0x19)
    golpe(r, 1, 0x78, 0x2B * 64 + 400, 0x2B * 64, 0x12)
    golpes_fuera(r, 2)
