#!/usr/bin/env python3
"""
kf2_tex.py - Qué aspecto tiene cada casilla de un nivel de King's Field II (suelo, pared y techo) y qué textura
de King's Field IV (las del 099.map, el Palacio de Oath) se le parece más.

Formatos (de github.com/AnatoliySolomichev/kings_field_2_re, FORMATS.md y tools/rtim.py, tools/tmd.py):
  - La memoria de vídeo de un nivel (1024 x 512 de u16) se monta con FDAT.T[96] y luego RTIM.T[nivel]: bloques
    con cabecera s16 x, y, w, h repetida dos veces y w * h halfwords.
  - Una página de 4 bits: tpage bits 0-3 = x / 64, bit 4 = y / 256; clut = (x / 16) | (y << 6).
  - RTMD.T[nivel] es un TMD de 240 objetos; cell[+5] elige el de cada casilla (>= 0xF0: roca). Las
    referencias a vértices son desplazamientos en bytes (8 por vértice).
"""

import struct

import numpy as np

VW, VH = 1024, 512


def leer_t(datos):
    n = struct.unpack_from("<H", datos, 0)[0]
    off = struct.unpack_from(f"<{n + 1}H", datos, 2)
    return [datos[off[i] * 2048:off[i + 1] * 2048] for i in range(n)]


# ---------------- memoria de vídeo ----------------
def _bloques(d):
    p = 0
    while p + 16 <= len(d):
        if d[p:p + 8] == d[p + 8:p + 16]:
            x, y, w, h = struct.unpack_from("<4h", d, p)
            if 0 <= x and 0 <= y and 0 < w and 0 < h and x + w <= VW and y + h <= VH and p + 16 + w * h * 2 <= len(d):
                yield x, y, w, h, d[p + 16:p + 16 + w * h * 2]
                p += 16 + w * h * 2
                continue
        p += 4


def vram_nivel(fdat, rtim, nivel, base=96):
    buf = np.zeros((VH, VW), np.uint16)
    for d in (fdat[base], rtim[nivel]):
        for x, y, w, h, data in _bloques(d):
            buf[y:y + h, x:x + w] = np.frombuffer(data, np.uint16).reshape(h, w)
    return buf


def pagina4(vram, tpage, clut):
    """RGBA 256 x 256 (uint8) de una página de 4 bits con su CLUT; el color 0 es transparente."""
    px0, py0 = (tpage & 0xF) * 64, ((tpage >> 4) & 1) * 256
    cx, cy = (clut & 0x3F) * 16, (clut >> 6) & 0x1FF
    pal16 = vram[cy, cx:cx + 16].astype(np.uint32)
    pal = np.zeros((16, 4), np.uint8)
    for k, c in enumerate([(pal16 & 31), (pal16 >> 5) & 31, (pal16 >> 10) & 31]):
        pal[:, k] = (c << 3) | (c >> 2)
    pal[:, 3] = np.where(pal16 == 0, 0, 255)
    hw = vram[py0:py0 + 256, px0:px0 + 64].astype(np.uint32)
    idx = np.stack([(hw >> (4 * k)) & 0xF for k in range(4)], axis=2).reshape(256, 256)
    return pal[idx]


# ---------------- modelos de las casillas ----------------
def objetos_tmd(d, por_8=True):
    """[(vértices, [(tpage, clut, uvs, refs)])] de un TMD (sin envoltorio), refs como índices de vértice.
    por_8: los índices van multiplicados por 8 (los RTMD del King's Field); los MO.T llevan el índice tal cual."""
    idv, flags, nobj = struct.unpack_from("<3I", d, 0)
    if idv not in (0x41, 0):            # el King's Field europeo (KF2 japonés) guarda 0 en vez de 0x41
        raise ValueError("No es un TMD")
    out = []
    for o in range(nobj):
        vt, nv, nt, nn, pt, npr, _ = struct.unpack_from("<7i", d, 12 + 28 * o)
        verts = [struct.unpack_from("<3h", d, 12 + vt + 8 * i) for i in range(nv)]
        normales = [struct.unpack_from("<3h", d, 12 + nt + 8 * i) for i in range(nn)]
        prims, p = [], 12 + pt
        for _ in range(npr):
            if p + 4 > len(d):
                break
            ilen, flag, mode = d[p + 1], d[p + 2], d[p + 3]
            body = d[p + 4:p + 4 + ilen * 4]
            p += 4 + ilen * 4
            quad, tex, iip, lit = bool(mode & 8), bool(mode & 4), bool(mode & 0x10), not (flag & 1)
            n = 4 if quad else 3
            hw = lambda i: struct.unpack_from("<H", body, i * 2)[0]
            q, uvs, tpage, clut = 0, [], None, None
            if tex:
                for k in range(n):
                    uvs.append((body[q * 2], body[q * 2 + 1]))
                    if k == 0:
                        clut = hw(q + 1)
                    elif k == 1:
                        tpage = hw(q + 1)
                    q += 2
            if not tex or not lit:
                q += 2
            resto = [hw(i) for i in range(q, len(body) // 2)]
            nref = None
            if lit and iip:
                vrefs = resto[1:2 * n:2]
                nref = resto[0] if resto else None
            else:
                if lit:
                    nref = resto[0] if resto else None
                    resto = resto[1:] if len(resto) >= 1 + n else resto
                vrefs = resto[:n]
            if not tex or len(vrefs) < 3:
                continue
            k8 = 8 if por_8 else 1
            refs = [r // k8 for r in vrefs]
            if max(refs) >= nv:
                continue
            ni = nref // k8 if nref is not None and nref // k8 < nn else None
            prims.append((tpage, clut, uvs, refs, normales[ni] if ni is not None else None))
        out.append((verts, prims))
    return out


def _clase(verts, refs):
    """'suelo', 'techo' o 'pared' por la normal (PlayStation: Y hacia abajo) y el área."""
    a, b, c = (np.array(verts[r], float) for r in refs[:3])
    nrm = np.cross(b - a, c - a)
    area = np.linalg.norm(nrm) / 2 * (2 if len(refs) == 4 else 1)
    if area <= 0:
        return None, 0.0
    ny = nrm[1] / (2 * area / (2 if len(refs) == 4 else 1))
    centro_y = np.mean([verts[r][1] for r in refs])
    if abs(ny) > 0.7:
        # el suelo de la casilla es la cara horizontal más baja (y mayor en PlayStation); techo, las altas
        return ("suelo" if centro_y > -900 else "techo"), area
    return "pared", area


def aspecto_objeto(verts, prims):
    """Para cada clase, la región de textura que más área cubre: (tpage, clut, u0, v0, u1, v1)."""
    mejor = {}
    for tpage, clut, uvs, refs, _n in prims:
        clase, area = _clase(verts, refs)
        if clase is None:
            continue
        us, vs = [u for u, _ in uvs], [v for _, v in uvs]
        # las texturas de las casillas están en cuadros alineados de 64 (o 128) téxeles de la página: se coge
        # el cuadro entero, no el trozo que pisa cada polígono, para que varios trozos sean la misma textura
        lado = 64 if max(max(us) - min(us), max(vs) - min(vs)) <= 64 else 128
        cu, cv = (min(us) + max(us)) // 2 // lado * lado, (min(vs) + max(vs)) // 2 // lado * lado
        clave = (tpage, clut, cu, cv, cu + lado, cv + lado)
        d = mejor.setdefault(clase, {})
        d[clave] = d.get(clave, 0.0) + area
    return {c: max(d, key=d.get) for c, d in mejor.items()}


def recorte(vram, clave, cache):
    tpage, clut, u0, v0, u1, v1 = clave
    if (tpage >> 7) & 3:            # solo páginas de 4 bits
        return None
    k = (tpage, clut)
    if k not in cache:
        cache[k] = pagina4(vram, tpage, clut)
    img = cache[k][v0:v1, u0:u1]
    return img if img.size and (img[..., 3] > 0).mean() > 0.5 else None


# ---------------- comparación con las texturas de KF4 ----------------
def _lab(rgb):
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def rasgos(img):
    """Color medio (Lab), contraste y cuánto detalle tiene: lo que hace que dos texturas se parezcan."""
    a = img[..., 3] > 0 if img.shape[-1] == 4 else np.ones(img.shape[:2], bool)
    rgb = img[..., :3].astype(float)
    lab = _lab(rgb[a]) if a.any() else np.zeros((1, 3))
    L = _lab(rgb)[..., 0]
    gx = np.abs(np.diff(L, axis=1)).mean() if L.shape[1] > 1 else 0
    gy = np.abs(np.diff(L, axis=0)).mean() if L.shape[0] > 1 else 0
    return np.array([*lab.mean(0), lab[:, 0].std(), (gx + gy) / 2])


def distancia(r1, r2):
    pesos = np.array([1.0, 1.6, 1.6, 0.6, 0.8])      # el tono pesa más que la luminosidad exacta
    return float(np.sqrt((((r1 - r2) * pesos) ** 2).sum()))


def texturas_kf4(d099):
    """{nombre: (clave (tbp, cbp), rasgos)} de las texturas opacas del 099.map que sirven de suelo/pared."""
    import kf4_tex as kt
    texs, _, _ = kt.load_map_textures(d099)
    out = {}
    for f, img in texs.values():
        if img is None or f["W"] < 32 or f["H"] < 32:
            continue
        img = np.asarray(img)
        if img.shape[-1] == 4 and (img[..., 3] < 100).mean() > 0.05:      # con agujeros: rejas, ventanas
            continue
        out[f"t{f['TBP']:04x}_{f['CBP']:04x}"] = ((f["TBP"], f["CBP"]), rasgos(img))
    return out


def casillas_nivel(fdat, rtim, rtmd, nivel):
    """{índice de objeto de casilla: {'suelo'|'pared'|'techo': rasgos}} del nivel."""
    vram = vram_nivel(fdat, rtim, nivel)
    objs = objetos_tmd(rtmd[nivel])
    cache, out, imgs = {}, {}, {}
    for i, (verts, prims) in enumerate(objs):
        asp = aspecto_objeto(verts, prims)
        r = {}
        for clase, clave in asp.items():
            img = recorte(vram, clave, cache)
            if img is not None:
                r[clase] = rasgos(img)
                imgs[(i, clase)] = img
        out[i] = r
    return out, imgs


# ---------------- elegir las texturas de un nivel ----------------
# los 14 huecos de textura del editor (todos de 4 bits, como las de KF2): primero los cuadrados
HUECOS = ["losas", "muro", "roca_gris", "musgo", "grava", "ladrillo", "estrias", "sillar", "roca", "nicho",
          "piedra_lisa", "banda", "madera", "friso"]


def _opaca(img):
    """La región de KF2 con el color 0 (transparente) relleno con el color medio de lo opaco."""
    img = img.copy()
    a = img[..., 3] > 0
    if a.any() and not a.all():
        img[~a, :3] = img[a, :3].mean(0).astype(np.uint8)
    img[..., 3] = 255
    return img


def texturas_nivel(fdat, rtim, rtmd, nivel, usos, base=96):
    """Para un nivel: {objeto de casilla: {'suelo'|'pared'|'techo': nombre de hueco}} y {hueco: imagen RGBA de KF2}.
    Las regiones de textura más usadas (por casillas) se quedan un hueco cada una; las demás van al hueco
    cuya textura más se les parece."""
    import collections
    vram = vram_nivel(fdat, rtim, nivel, base)
    objs = objetos_tmd(rtmd[nivel])
    uso = collections.Counter(t for t in usos if t < 0xF0)
    cache, regiones, por_obj = {}, collections.Counter(), {}
    imgs = {}
    for oi, n in uso.items():
        if oi >= len(objs):
            continue
        asp = aspecto_objeto(*objs[oi])
        por_obj[oi] = {}
        for clase, clave in asp.items():
            img = recorte(vram, clave, cache)
            if img is None:
                continue
            region = clave
            imgs[region] = _opaca(img)
            regiones[region] += n
            por_obj[oi][clase] = region
    elegidas = [r for r, _ in regiones.most_common(len(HUECOS))]
    hueco_de = {r: HUECOS[k] for k, r in enumerate(elegidas)}
    rasgo = {r: rasgos(imgs[r]) for r in imgs}
    for r in imgs:
        if r not in hueco_de:
            hueco_de[r] = hueco_de[min(elegidas, key=lambda e: distancia(rasgo[r], rasgo[e]))]
    aspecto = {oi: {c: hueco_de[r] for c, r in d.items()} for oi, d in por_obj.items()}
    return aspecto, {hueco_de[r]: imgs[r] for r in elegidas}


# ---------------- meter las texturas de KF2 en los huecos del 099.map ----------------
def _direcciones4(bp, bw, w, h):
    """(byte, nibble alto?) en la VRAM de cada píxel de una textura PSMT4, como la lee el GS."""
    import kf4_tex as kt
    y, x = np.mgrid[0:h, 0:w]
    bw2 = max(1, bw >> 1)
    page = x // 128 + (y // 128) * bw2
    px, py = x % 128, y % 128
    block = kt.BLOCK4[px // 32 + (py // 16) * 4]
    bx, by = px % 32, py % 16
    col = by // 4
    cy = by % 4
    cw = kt.COLW4[col & 1, bx + cy * 32]
    cb = kt.COLB4[bx + cy * 32]
    a = bp * 256 + ((page * 2048 + block * 64 + col * 16 + cw) * 4) + (cb >> 1)
    return a % kt.VRAM_BYTES, (cb & 1).astype(bool)


def a_hueco(img, w, h):
    """La textura de KF2 (16 colores) al tamaño del hueco, por vecino más cercano: índices y paleta de 16."""
    sh, sw = img.shape[:2]
    ys = (np.arange(h) * sh // h)
    xs = (np.arange(w) * sw // w)
    big = img[ys][:, xs]
    colores, idx = np.unique(big.reshape(-1, 4), axis=0, return_inverse=True)
    if len(colores) > 16:          # no debería pasar (KF2 usa 16 colores); por si acaso, los 16 más usados
        cuenta = np.bincount(idx.reshape(-1))
        top = np.argsort(-cuenta)[:16]
        pal = colores[top].astype(float)
        d = ((colores[:, None, :3].astype(float) - pal[None, :, :3]) ** 2).sum(-1)
        idx = d.argmin(1)[idx.reshape(-1)]
        colores = colores[top]
    pal = np.zeros((16, 4), np.uint8)
    pal[:len(colores)] = colores
    pal[:, 3] = 0x80                                   # opaco en el GS
    return idx.reshape(h, w).astype(np.uint8), pal


def inyectar(tex_blob, cambios, log=None):
    """tex_blob: el bloque de texturas de 099.map; cambios: {(tbp, cbp): imagen RGBA}. Escribe cada imagen en
    el sitio de esa textura (mismo tamaño y formato) y devuelve el bloque con las subidas rehechas."""
    import kf4_tex as kt
    blob = bytearray(tex_blob)
    vram, ups = kt.upload_map_textures(bytes(blob), 0, len(blob))
    # qué texturas hay (TBP, CBP, TBW, W, H) se saca de cómo se usan: aquí basta el formato de los huecos,
    # que es PSMT4 y se conoce por el nombre (kf4_editor.TEXTURAS) y el tamaño que se pase
    for (tbp, cbp, tbw, w, h), img in cambios.items():
        idx, pal = a_hueco(img, w, h)
        a, alto = _direcciones4(tbp, tbw, w, h)
        bajo = ~alto        # dos píxeles por byte: primero los nibbles bajos y luego los altos
        vram[a[bajo]] = (vram[a[bajo]] & 0xF0) | idx[bajo]
        vram[a[alto]] = (vram[a[alto]] & 0x0F) | (idx[alto] << 4)
        ca = kt.addr32(cbp, 1, *np.mgrid[0:2, 0:8][::-1]).reshape(-1)        # CLUT de 4 bits: 8 x 2
        for k in range(4):
            vram[ca + k] = pal[:, k]
    for u in ups:          # se rehacen todas las subidas desde la VRAM nueva
        y, x = np.mgrid[u["y"]:u["y"] + u["h"], u["x"]:u["x"] + u["w"]]
        a = kt.addr32(u["dbp"], max(1, u["dbw"]), x, y).reshape(-1)
        datos = np.stack([vram[(a + k) % kt.VRAM_BYTES] for k in range(4)], -1).reshape(-1).tobytes()
        n = min(len(datos), u["bytes"])
        blob[u["offset"] + 128:u["offset"] + 128 + n] = datos[:n]
    if log is not None:
        log.append(f"Texturas de King's Field II metidas en {len(cambios)} huecos del 099")
    return bytes(blob)
