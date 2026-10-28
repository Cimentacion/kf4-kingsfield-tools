#!/usr/bin/env python3
"""
kf4_cruz.py - Texturas de la cruz de equipo rápido: las ilustraciones de los objetos del propio juego
(menu/select2/iXXXX.mod, las del menú) reducidas y en paleta, y el marco de cada casilla.

Se guardan dentro de 099.map en un bloque con esta forma (todo alineado a 16):
  +0x000  "KF4CRUZ1" + 8 bytes
  +0x010  ilustración de cada arma (índice 0-69 -> trozo de la tabla, 0xFF ninguna)
  +0x060  de cada escudo (0-25)
  +0x080  de cada objeto (id 0-31: consumibles)
  +0x0A0  8 sprites del HUD (ScreenSprite, 0x40 bytes): 4 marcos y 4 ilustraciones (derecha, izquierda,
          arriba, abajo)
  +0x2A0  cifras de la vida; +0x2D0 letras (OFF_TEXTO_*)
  +0x500  tabla de texturas (la de TextureTable_QueueOne): cabecera, entradas y trozos con las subidas
          GIF a la memoria de vídeo. El trozo 0 es el marco (y deja el ALPHA normal); los demás, ilustraciones.
Cada fotograma, el HUD sube el marco y la ilustración de cada casilla a la zona de texturas del HUD (que el
HUD ya ha usado y vuelve a subir en el siguiente fotograma) y los dibuja.
"""

import struct

import numpy as np

FIRMA = b"KF4CRUZ1"
OFF_ARMAS, OFF_ESCUDOS, OFF_OBJETOS, OFF_SPRITES = 0x10, 0x60, 0x80, 0xA0
# letras (nombre y maná de la magia, cantidad del objeto): TEX0 y TEX1 del atlas, su trozo, "MP" (texto del juego,
# u16 + 0xFFFF) y, por cada código de letra del juego (el byte bajo de los u16 de 0x08xx), su (u, v) en el atlas
OFF_TEXTO_TEX, OFF_TEXTO_TROZO, OFF_TEXTO_MP, OFF_TEXTO_MAPA = 0x2D0, 0x2E0, 0x2E8, 0x300
OFF_MAGIAS = 0x500                         # ilustración de cada magia (id 0-90 -> trozo, 0xFF ninguna)
OFF_FUENTES = 0x560                        # fuentes que curan: u32 n, f32 alto², 8 de relleno, y 4 x (x, y, z, radio²)
FUENTES_MAX = 4
OFF_TABLA = 0x5B0
# cifras de la vida con la fuente del menú del juego (menu/font.tmr): TEX0 y TEX1 del sprite, (u, ancho) de
# "0".."9" y "/", y el índice de su trozo en la tabla de texturas
OFF_CIFRAS_TEX, OFF_CIFRAS_TAB, OFF_CIFRAS_TROZO = 0x2A0, 0x2B0, 0x2C6
CIFRAS_W, CIFRAS_H = 128, 32               # textura de las cifras (va en la página de la casilla de abajo)
CIFRAS_DESTINO = 4
TEXTO_DESTINO = 3                          # el atlas de letras va en la página de la casilla de arriba (la magia no
                                           # lleva ilustración); los objetos, abajo (destino 4, con las cifras)
LETRA_W, LETRA_H = 7, 14                   # letra en el atlas, ya reducida (la de la fuente es de 10 x 20)
ATLAS_COLS, ATLAS_FILAS = 18, 8            # atlas de 128 x 256 a 4 bits (páginas 3 y 4): 144 letras
CIFRA_W, CIFRA_H, CIFRA_V = 9, 18, 112     # cifras grandes (maná, cantidad): fila debajo de las letras
ANCHO, ALTO = 64, 64                       # textura de cada casilla (8 bits, 256 colores)
# memoria de vídeo: la del HUD (gage.tx2 va de 0x3540 a 0x3790, sus paletas de 0x3ED0 a 0x3EEC)
TBP = [0x3540, 0x3560, 0x3580, 0x35A0, 0x35C0]     # marco, derecha, izquierda, arriba, abajo (una página cada una)
CBP = [0x3ED0, 0x3ED4, 0x3ED8, 0x3EDC, 0x3EE0]
# casillas en píxeles del HUD de la versión PAL (512 x 512): x, y, ancho, alto. Abajo a la izquierda.
# el HUD se ve estirado en horizontal (x 2,53 y 1,89 por píxel en pantalla): 40 x 54 es casi cuadrado a la vista
CASILLA_W, CASILLA_H = 40, 54
CASILLAS = [(100, 349), (14, 349), (57, 292), (57, 406)]  # derecha (arma), izquierda (escudo), arriba, abajo
ICONO_W, ICONO_H = 44, 59                   # casi como la casilla: el dibujo apenas se sale del marco
ICONO_DX, ICONO_DY = 1, -2                  # y un poco hacia arriba a la derecha
ICONO_ARMA_W, ICONO_ARMA_H = 56, 75         # el arma, más grande: se sale del marco
BRILLO_ICONO = 1.3                         # las ilustraciones del menú son oscuras para el fondo del HUD


def _hud(px):
    return (px + 0x10 + 0x700) << 4          # Hud_InitSprite de SLES_509.20


def ilustracion(d):
    """Imagen RGBA (128 x 256 x 4, alfa del GS 0-0x80) de un menu/select2/iXXXX.mod."""
    px = np.frombuffer(d[0x1B0:0x1B0 + 0x20000], np.uint8).reshape(128, 256, 4)
    return px.copy()


def _reducir(img, w, h):
    """Promedio por áreas con el color premultiplicado por el alfa."""
    H, W = img.shape[:2]
    f = img.astype(np.float64)
    a = f[..., 3:4] / 128.0
    pre = np.concatenate([f[..., :3] * a, f[..., 3:4]], axis=2)
    ys = np.linspace(0, H, h + 1).astype(int)
    xs = np.linspace(0, W, w + 1).astype(int)
    out = np.zeros((h, w, 4))
    for j in range(h):
        for i in range(w):
            blk = pre[ys[j]:max(ys[j] + 1, ys[j + 1]), xs[i]:max(xs[i] + 1, xs[i + 1])]
            out[j, i] = blk.reshape(-1, 4).mean(axis=0)
    a = out[..., 3:4] / 128.0
    rgb = np.where(a > 1e-3, out[..., :3] / np.maximum(a, 1e-3), 0)
    return np.concatenate([np.clip(rgb, 0, 255), np.clip(out[..., 3:4], 0, 128)], axis=2)


def icono(img):
    """La ilustración recortada a lo que tiene dibujo, en un cuadrado, a 64 x 64 (RGBA float)."""
    # el menú dibuja la ilustración (256 x 128) en un cuadrado: cada píxel es el doble de alto que de ancho
    rot = np.repeat(img, 2, axis=0)
    m = rot[..., 3] > 6
    if not m.any():
        return np.zeros((ALTO, ANCHO, 4))
    ys, xs = np.where(m)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    h, w = y1 - y0, x1 - x0
    # caja cuadrada, casi sin margen: el dibujo llena la casilla
    H = max(h, w) * 1.04
    W = H
    cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
    lienzo = np.zeros((int(H) + 2, int(W) + 2, 4), np.uint8)
    oy, ox = int(cy - H / 2), int(cx - W / 2)
    for yy in range(lienzo.shape[0]):
        sy = oy + yy
        if 0 <= sy < rot.shape[0]:
            sx0, sx1 = max(0, ox), min(rot.shape[1], ox + lienzo.shape[1])
            if sx1 > sx0:
                lienzo[yy, sx0 - ox:sx1 - ox] = rot[sy, sx0:sx1]
    return _reducir(lienzo, ANCHO, ALTO)


def marco():
    """El fondo de una casilla: piedra oscura con un degradado y el borde gastado (RGBA float)."""
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:ALTO, 0:ANCHO]
    dx = np.minimum(xx, ANCHO - 1 - xx) / (ANCHO / 2)
    dy = np.minimum(yy, ALTO - 1 - yy) / (ALTO / 2)
    borde = np.minimum(dx, dy)                             # 0 en el borde, ~1 en el centro
    ruido = rng.normal(0, 1, (ALTO, ANCHO))
    base = 22 + 34 * np.clip(borde * 1.6, 0, 1) + 4 * ruido
    rgb = np.stack([base * 1.04, base, base * 0.92], axis=2)
    a = np.full((ALTO, ANCHO), 0x6C, float)
    bx, by = np.minimum(xx, ANCHO - 1 - xx), np.minimum(yy, ALTO - 1 - yy)
    filo = ((bx >= 1) & (bx <= 2) & (by >= 1)) | ((by >= 1) & (by <= 2) & (bx >= 1))
    rgb[filo] = np.array([96, 90, 80]) + rng.normal(0, 8, (filo.sum(), 1))
    a[filo] = 0x76
    fuera = (bx == 0) | (by == 0)
    rgb[fuera] = 6
    a[fuera] = np.where(rng.random(fuera.sum()) < 0.25, 0x30, 0x80)
    return np.concatenate([np.clip(rgb, 0, 255), a[..., None]], axis=2)


def paleta(img, n=256):
    """(índices, paleta n x RGBA) con k-medias sencillo."""
    px = img.reshape(-1, 4)
    q = np.round(px / np.array([4, 4, 4, 4])) * np.array([4, 4, 4, 4])
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    if len(uniq) <= n:
        pal = np.zeros((n, 4))
        pal[:len(uniq)] = uniq
        return inv.astype(np.uint8), np.clip(pal, 0, 255).astype(np.uint8)
    w = np.array([1.0, 1.0, 1.0, 2.0])
    rng = np.random.default_rng(1)
    cent = px[rng.choice(len(px), n, replace=False)].astype(float)
    for _ in range(10 if n > 16 else 16):
        d = (((px[:, None, :] - cent[None, :, :]) * w) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        for k in range(n):
            sel = px[lab == k]
            if len(sel):
                cent[k] = sel.mean(axis=0)
    d = (((px[:, None, :] - cent[None, :, :]) * w) ** 2).sum(axis=2)
    lab = d.argmin(axis=1)
    return lab.astype(np.uint8), np.clip(np.round(cent), 0, 255).astype(np.uint8)


def _clut_csm1(pal):
    """Orden de una paleta de 256 colores en el GS (CSM1): se cambian de sitio las filas 8-15 y 16-23 de cada 32."""
    out = np.zeros_like(pal)
    for i in range(256):
        j = (i & 0xE7) | ((i & 0x08) << 1) | ((i & 0x10) >> 1)
        out[j] = pal[i]
    return out


def _gif_ad(regs, eop=False):
    tag = len(regs) | ((1 if eop else 0) << 15) | (0 << 58) | (1 << 60)
    out = struct.pack("<QQ", tag, 0xE)
    for reg, val in regs:
        out += struct.pack("<QQ", val, reg)
    return out


def _gif_imagen(datos):
    assert len(datos) % 16 == 0
    tag = (len(datos) // 16) | (2 << 58)
    return struct.pack("<QQ", tag, 0) + datos


def _subida(dbp, dbw, dpsm, w, h, datos):
    return (_gif_ad([(0x50, (dbp << 32) | (dbw << 48) | (dpsm << 56)), (0x51, 0), (0x52, w | (h << 32)), (0x53, 0)])
            + _gif_imagen(datos))


def trozo(destino, img, poner_alpha=False):
    """Trozo de la tabla de texturas: subidas de la imagen y la paleta a su sitio, y TEXFLUSH."""
    idx, pal = paleta(img)
    gif = b""
    if poner_alpha:
        gif += _gif_ad([(0x42, 0x44)])                     # ALPHA_1: mezcla normal (el HUD lo deja aditivo)
    gif += _subida(TBP[destino], 2, 0x13, img.shape[1], img.shape[0], idx.tobytes())
    gif += _subida(CBP[destino], 1, 0x00, 16, 16, _clut_csm1(pal).tobytes())
    gif += _gif_ad([(0x3F, 0)], eop=True)                 # TEXFLUSH
    qwc = len(gif) // 16
    # como Texture_BuildPacket: etiqueta DMA (qwc + 1 cuádruples) y, delante de los datos GIF, el código VIF
    # DIRECTHL: la cadena de dibujo va por el canal VIF1 y sin él el VIF lee el GIF como órdenes y se cuelga
    return struct.pack("<IIII", qwc + 1, 0, 0, 0) + struct.pack("<IIII", 0, 0, 0, 0x51000000 | qwc) + gif


def paleta16(img):
    """(índices 2D, paleta 16 x RGBA) para una ilustración: el 0 es el fondo transparente y los otros 15 salen de
    k-medias solo sobre lo que tiene dibujo (con todo, medio cuadro de fondo se comía colores)."""
    h, w = img.shape[:2]
    px = img.reshape(-1, 4).astype(float)
    dib = px[:, 3] > 6
    idx = np.zeros(len(px), np.uint8)
    pal = np.zeros((16, 4))
    if dib.any():
        sub = px[dib]
        peso = np.array([1.0, 1.0, 1.0, 1.5])
        rng = np.random.default_rng(1)
        # inicio k-medias++: cada centro nuevo, lejos de los que ya hay
        cent = [sub[rng.integers(len(sub))]]
        for _ in range(14):
            d = np.min([(((sub - c) * peso) ** 2).sum(axis=1) for c in cent], axis=0)
            if d.sum() <= 0:
                break
            cent.append(sub[rng.choice(len(sub), p=d / d.sum())])
        cent = np.array(cent)
        for _ in range(20):
            d = (((sub[:, None, :] - cent[None, :, :]) * peso) ** 2).sum(axis=2)
            lab = d.argmin(axis=1)
            for k in range(len(cent)):
                sel = sub[lab == k]
                if len(sel):
                    cent[k] = sel.mean(axis=0)
        idx[dib] = lab + 1
        pal[1:1 + len(cent)] = cent
    return idx.reshape(h, w), np.clip(np.round(pal), 0, 255).astype(np.uint8)


def trozo_icono(destino, img, colores=256):
    """La ilustración de una casilla: de 8 bits (256 colores) o, para ahorrar sitio en el mapa, de 4 (16 colores:
    la mitad de bytes y una paleta de 64 en vez de 1024)."""
    if colores == 256:
        return trozo(destino, img)
    idx, pal = paleta16(img)
    nib = (idx[:, 0::2] & 15) | ((idx[:, 1::2] & 15) << 4)
    gif = _subida(TBP[destino], 2, 0x14, img.shape[1], img.shape[0], nib.astype(np.uint8).tobytes())
    gif += _subida(CBP[destino], 1, 0x00, 8, 2, np.asarray(pal, np.uint8).tobytes())
    gif += _gif_ad([(0x3F, 0)], eop=True)
    qwc = len(gif) // 16
    return struct.pack("<IIII", qwc + 1, 0, 0, 0) + struct.pack("<IIII", 0, 0, 0, 0x51000000 | qwc) + gif


def trozo4(destino, idx, pal16, poner_alpha=True):
    """Trozo de una textura de 4 bits (128 de ancho) con su paleta de 16 colores (CT32, 8 x 2)."""
    h, w = idx.shape
    assert w == 128
    nib = (idx[:, 0::2] & 15) | ((idx[:, 1::2] & 15) << 4)
    gif = b""
    if poner_alpha:
        gif += _gif_ad([(0x42, 0x44)])
    gif += _subida(TBP[destino], 2, 0x14, w, h, nib.astype(np.uint8).tobytes())
    gif += _subida(CBP[destino], 1, 0x00, 8, 2, np.asarray(pal16, np.uint8).tobytes())
    gif += _gif_ad([(0x3F, 0)], eop=True)
    qwc = len(gif) // 16
    return struct.pack("<IIII", qwc + 1, 0, 0, 0) + struct.pack("<IIII", 0, 0, 0, 0x51000000 | qwc) + gif


def tex0_4(destino):
    return (TBP[destino] | (2 << 14) | (0x14 << 20) | (7 << 26) | (8 << 30) | (1 << 34) | (CBP[destino] << 37)
            | (1 << 61))


def letras_del_menu(d):
    """De font.tmr (la fuente de los textos): función código -> máscara 20 x 10 (1 = tinta) de las letras de media anchura (las de los
    nombres de objetos y magias: u16 0x08xx). En el archivo están en filas de 50 de 10 x 20 píxeles; la tinta es
    el bit 3 a cero; la fila empieza 289 píxeles después del principio de los datos."""
    raw = np.frombuffer(d[0x20:0x20 + 0x20000], np.uint8)
    px = np.zeros(512 * 512, np.uint8)
    px[0::2], px[1::2] = raw & 15, raw >> 4
    tinta = np.roll(((px >> 3) & 1) == 0, -289).reshape(512, 512)

    def letra(c):
        r, k = divmod(c, 50)
        m = tinta[r * 20:r * 20 + 20, k * 10:k * 10 + 10].astype(np.uint8)
        m[:, 9] = 0                             # la última columna es el borde de la letra de al lado
        return m
    # comprobación: el "0" (0x10) y la "M" (0x2D) tienen tinta y el espacio no
    if not (letra(0x10).sum() > 20 and letra(0x2D).sum() > 20 and letra(0).sum() < 5):
        return None
    return letra


def nombres_magia(mg):
    """Los u16 de los nombres de magia de param/magic.prm (0x110 bytes por magia, el nombre al principio)."""
    out = {}
    for i in range(1, min(91, len(mg) // 0x110)):
        cad = []
        for k in range(0, 0x34, 2):
            c = struct.unpack_from("<H", mg, i * 0x110 + k)[0]
            if c == 0xFFFF or c & 0x8000:
                break
            cad.append(c)
        out[i] = cad
    return out


def _reducir_letra(m, w, h, refuerzo):
    """La letra (20 x 9 de tinta 0/1) reducida por áreas a w x h, con la tinta reforzada (los trazos de un
    píxel no se pierden), en 0..1."""
    f = m.astype(float)
    H, W = f.shape
    grande = np.kron(f, np.ones((h, w)))
    out = grande.reshape(h, H, w, W).mean(axis=(1, 3))
    return np.clip(out * refuerzo, 0, 1)


def atlas_letras(letra, codigos):
    """(índices 128 x 256 a 4 bits = 16 niveles de alfa, paleta, mapa de 256 x (u, v) con 0xFF si no está, n) de
    esas letras ya reducidas al tamaño al que se dibujan (un téxel por píxel del HUD: nítidas), y debajo una fila
    de cifras más grandes (CIFRA_*) para el maná y las cantidades."""
    img = np.zeros((256, 128), np.uint8)
    mapa = bytearray(b"\xff" * 512)
    n = 0
    for c in sorted(codigos):
        if c == 0 or n >= ATLAS_COLS * ATLAS_FILAS:
            continue
        m = letra(c)[:, :9]
        if m.sum() == 0:
            continue
        u, v = (n % ATLAS_COLS) * LETRA_W, (n // ATLAS_COLS) * LETRA_H
        img[v:v + LETRA_H, u:u + LETRA_W] = np.round(_reducir_letra(m, LETRA_W, LETRA_H, 1.6) * 15)
        mapa[2 * c:2 * c + 2] = bytes([u, v])
        n += 1
    for k in range(10):
        img[CIFRA_V:CIFRA_V + CIFRA_H, k * CIFRA_W:(k + 1) * CIFRA_W] = np.round(
            _reducir_letra(letra(0x10 + k)[:, :9], CIFRA_W, CIFRA_H, 1.4) * 15)
    pal = np.zeros((16, 4), np.uint8)
    for i in range(16):
        pal[i] = (0x80, 0x80, 0x80, round(i * 0x80 / 15))
    return img, pal, mapa, n


def tex0(destino, ancho=ANCHO, alto=ALTO, psm=0x13):
    return (TBP[destino] | (2 << 14) | (psm << 20) | ((ancho.bit_length() - 1) << 26) | ((alto.bit_length() - 1) << 30) | (1 << 34) | (0 << 35)
            | (CBP[destino] << 37) | (1 << 61))


def sprite(destino, x, y, w, h, rgba=(0x80, 0x80, 0x80, 0x80), psm=0x13):
    """ScreenSprite (0x40 bytes) como los que prepara Hud_InitSprite."""
    b = bytearray(0x40)
    struct.pack_into("<QQ", b, 0, tex0(destino, psm=psm), 0x60)
    struct.pack_into("<i", b, 0x10, 0x156)
    b[0x14:0x18] = bytes(rgba)
    struct.pack_into("<HHIii", b, 0x20, _hud(x), _hud(y), 0, 0, 0)
    struct.pack_into("<HHIii", b, 0x30, _hud(x + w), _hud(y + h), 0, ANCHO << 4, ALTO << 4)
    return bytes(b)


def cifras_del_menu(d):
    """De menu/font.tmr (PSMT4 512 x 512; la primera fila de la fuente de números está en los 2 bits altos con
    la segunda paleta): imagen RGBA de "0".."9" y "/" en fila, [(u, ancho)] y el alto."""
    data_off, tam, _, clut2 = struct.unpack_from("<4I", d, 0)
    img = np.frombuffer(d[0x20:0x20 + 0x20000], np.uint8)
    px = np.zeros(512 * 512, np.uint8)
    px[0::2], px[1::2] = img & 15, img >> 4
    px = px.reshape(512, 512)
    pal = struct.unpack_from("<16I", d, clut2)
    gris = np.array([(c >> 8) & 0xFF for c in pal], float)
    opaco = np.array([(c >> 24) & 0xFF for c in pal], float)
    g, a = gris[px[1:20]], opaco[px[1:20]]                 # la fila de "./0123456789:"
    cols = a.max(0) > 0
    trozos, x = [], 0
    while x < 512:
        if cols[x]:
            x0 = x
            while x < 512 and cols[x]:
                x += 1
            trozos.append((x0, x))
        else:
            x += 1
    # 0x20.. hasta el primer bloque que junta letras: se buscan "/" y "0".."9" por su posición en esa fila
    if len(trozos) < 25:
        return None
    bar = min(range(len(trozos)), key=lambda i: abs(trozos[i][0] - 150))          # "/" (150-159 en SLES_509.20)
    if not all(5 <= trozos[bar + 1 + k][1] - trozos[bar + 1 + k][0] <= 12 for k in range(10)):
        return None
    glifos = [trozos[bar + 1 + k] for k in range(10)] + [trozos[bar]]
    out = np.zeros((CIFRAS_H, CIFRAS_W, 4))
    tabla, u = [], 0
    for x0, x1 in glifos:
        w = x1 - x0
        out[0:19, u:u + w, :3] = g[:, x0:x1, None]
        out[0:19, u:u + w, 3] = a[:, x0:x1]
        tabla.append((u, w))
        u += w + 1
    if u > CIFRAS_W:
        return None
    return out, tabla, 19


_HECHO = {}


def poner_fuentes(bloque, puntos, radio=450.0, alto=300.0):
    """Escribe en el bloque las fuentes que curan (puntos en el espacio del juego, cm). Devuelve el bloque."""
    b = bytearray(bloque)
    puntos = list(puntos)[:FUENTES_MAX]
    struct.pack_into("<If", b, OFF_FUENTES, len(puntos), alto * alto)
    for k, (x, y, z) in enumerate(puntos):
        struct.pack_into("<4f", b, OFF_FUENTES + 16 + 16 * k, x, y, z, radio * radio)
    return bytes(b)


def construir_bloque(leer, log, colores=256):
    """leer(nombre) -> bytes o None. Devuelve el bloque o None si no hay ilustraciones. colores: 256 o 16 (las
    ilustraciones de las casillas a 4 bits: el bloque ocupa casi la mitad)."""
    nam = leer("param/item_nam.prm")
    if not nam:
        log.append("Cruz: sin item_nam.prm, sin ilustraciones")
        return None
    if (nam, colores) in _HECHO:            # el editor comprueba el mapa muchas veces: se hace una sola
        bloque, lineas = _HECHO[(nam, colores)]
        log.extend(lineas)
        return bloque
    n0 = len(log)
    bloque = _construir(leer, nam, log, colores)
    if bloque is not None:
        _HECHO[(nam, colores)] = (bloque, log[n0:])
    return bloque


def _construir(leer, nam, log, colores=256):
    modelo = [struct.unpack_from("<H", nam, i * 64 + 0x30)[0] for i in range(len(nam) // 64)]
    cache = {}

    def ilu(item):
        m = modelo[item] if item < len(modelo) else 0
        if not m:
            return None
        if m not in cache:
            d = leer(f"menu/select2/i{m:04d}.mod")
            img = icono(ilustracion(d)) if d and len(d) >= 0x1B0 + 0x20000 else None
            if img is not None:
                img[..., :3] = np.clip(img[..., :3] * BRILLO_ICONO, 0, 255)
            cache[m] = img
        return cache[m]
    trozos = [trozo(0, marco(), poner_alpha=True)]
    por_destino = {}
    mapas = {OFF_ARMAS: bytearray(b"\xff" * 0x50), OFF_ESCUDOS: bytearray(b"\xff" * 0x20),
             OFF_OBJETOS: bytearray(b"\xff" * 0x20)}
    grupos = [(OFF_ARMAS, 1, range(1, 70), 150), (OFF_ESCUDOS, 2, range(1, 26), 220), (OFF_OBJETOS, 4, range(1, 31), 0)]
    for off, destino, indices, base in grupos:
        for k in indices:
            item = base + k
            m = modelo[item] if item < len(modelo) else 0
            img = ilu(item)
            if img is None:
                continue
            clave = (destino, m)
            if clave not in por_destino:
                por_destino[clave] = len(trozos)
                trozos.append(trozo_icono(destino, img, colores))
            mapas[off][k] = por_destino[clave]
    if len(trozos) == 1:
        log.append("Cruz: no encuentro las ilustraciones de menu/select2; la cruz va sin dibujos")
    # magias: menu/select/mNNNN.mod (las del menú de magia, mismo formato); las repetidas (niveles) una vez
    mapas[OFF_MAGIAS] = bytearray(b"\xff" * 0x60)
    por_imagen = {}
    n_mag = 0
    for i in range(1, 91):
        d = leer(f"menu/select/m{(i - 1) // 3 * 3 + 1:04d}.mod")     # la del nivel 1 para los tres niveles
        if not d or len(d) < 0x1B0 + 0x20000:
            continue
        clave = hash(d[0x1B0:0x1B0 + 0x20000])
        if clave not in por_imagen:
            img = icono(ilustracion(d))
            img[..., :3] = np.clip(img[..., :3] * BRILLO_ICONO, 0, 255)
            por_imagen[clave] = len(trozos)
            trozos.append(trozo_icono(3, img, colores))
            n_mag += 1
        mapas[OFF_MAGIAS][i] = por_imagen[clave]
    log.append(f"Cruz: {n_mag} ilustraciones de magia" if n_mag else "Cruz: no encuentro menu/select/mNNNN.mod (magia sin dibujo)")
    fuente = leer("menu/font.tmr")
    cif = cifras_del_menu(fuente) if fuente and len(fuente) >= 0x20 + 0x20000 else None
    cifras_datos = None
    if cif:
        img_c, tabla_c, _ = cif
        cifras_datos = (len(trozos), tabla_c)
        trozos.append(trozo(CIFRAS_DESTINO, img_c, poner_alpha=True))
    texto_datos = None
    fuente_t = leer("font.tmr")                 # la fuente de los textos del juego (la de menu/ es otra)
    letra = letras_del_menu(fuente_t) if fuente_t and len(fuente_t) >= 0x20 + 0x20000 else None
    mg = leer("param/magic.prm")
    if letra and mg:
        # todas las letras de media anchura (el juego puede ir en otro idioma que el que se lee aquí)
        codigos = set(range(1, 100)) | set(range(150, 200))    # la fila 100-149 son cifras y signos repetidos
        img_t, pal_t, mapa_t, n_t = atlas_letras(letra, codigos)
        texto_datos = (len(trozos), mapa_t, n_t, len(codigos))
        trozos.append(trozo4(TEXTO_DESTINO, img_t, pal_t))
    # sprites: marcos y luego ilustraciones (derecha, izquierda, arriba, abajo)
    spr = b""
    for (x, y) in CASILLAS:
        spr += sprite(0, x, y, CASILLA_W, CASILLA_H)
    for c, (x, y) in enumerate(CASILLAS):
        # el arma (derecha) con su tamaño de antes, que se veía bien; los demás, casi como la casilla
        iw, ih, dx, dy = (ICONO_ARMA_W, ICONO_ARMA_H, 3, -4) if c == 0 else (ICONO_W, ICONO_H, ICONO_DX, ICONO_DY)
        spr += sprite(1 + c, x + (CASILLA_W - iw) // 2 + dx, y + (CASILLA_H - ih) // 2 + dy, iw, ih,
                      psm=0x13 if colores == 256 else 0x14)
    # tabla de texturas: cabecera, entradas y trozos (las posiciones cuentan desde la cabecera)
    n = len(trozos)
    pos = 0x10 + n * 0x10
    entradas, cuerpo = b"", b""
    for t in trozos:
        entradas += struct.pack("<IIII", pos + len(cuerpo), 0, 0, 0)
        cuerpo += t
    tabla = struct.pack("<IIII", len(cuerpo), n, 0, 0) + entradas + cuerpo
    bloque = bytearray(OFF_TABLA)
    bloque[0:8] = FIRMA
    for off, m in mapas.items():
        bloque[off:off + len(m)] = m
    bloque[OFF_SPRITES:OFF_SPRITES + len(spr)] = spr
    if cifras_datos:
        i_c, tabla_c = cifras_datos
        struct.pack_into("<QQ", bloque, OFF_CIFRAS_TEX, tex0(CIFRAS_DESTINO, CIFRAS_W, CIFRAS_H), 0x60)
        for k, (u, w) in enumerate(tabla_c):
            bloque[OFF_CIFRAS_TAB + 2 * k:OFF_CIFRAS_TAB + 2 * k + 2] = bytes([u, w])
        bloque[OFF_CIFRAS_TROZO] = i_c
    else:
        bloque[OFF_CIFRAS_TROZO] = 0xFF
    if texto_datos:
        i_t, mapa_t, _, _ = texto_datos
        struct.pack_into("<QQ", bloque, OFF_TEXTO_TEX, tex0_4(TEXTO_DESTINO), 0x60)
        bloque[OFF_TEXTO_TROZO] = i_t
        bloque[OFF_TEXTO_MP:OFF_TEXTO_MP + 6] = struct.pack("<HHH", 0x082D, 0x0830, 0xFFFF)
        bloque[OFF_TEXTO_MAPA:OFF_TEXTO_MAPA + 512] = mapa_t
    else:
        bloque[OFF_TEXTO_TROZO] = 0xFF
    bloque += tabla
    bloque += bytes((-len(bloque)) % 16)
    # al final, 16 bytes con el tamaño del bloque en su última palabra: el código lo encuentra hacia atrás desde
    # donde empieza la colisión del mapa (va justo antes), sea del tamaño que sea en cada mapa
    bloque += bytes(12) + struct.pack("<I", len(bloque) + 16)
    log.append("Cruz: " + (f"letras del menú para la magia y las cantidades ({texto_datos[2]} de {texto_datos[3]})"
                           if texto_datos else "sin letras (no encontré font.tmr o param/magic.prm)"))
    log.append(f"Cruz: {n - 1 - (1 if cifras_datos else 0) - (1 if texto_datos else 0)} ilustraciones del juego"
               + (" y las cifras del menú para la vida" if cifras_datos else " (sin cifras del menú: no encontré menu/font.tmr)")
               + (" de 16 colores" if colores != 256 else "")
               + f" ({len(bloque) // 1024} KB dentro del mapa)")
    return bytes(bloque)
