#!/usr/bin/env python3
"""
kf4_tex.py - Saca las texturas de un mapa de King's Field IV (.map) emulando la VRAM
de la PS2 (4 MB). Las subidas del bloque de texturas del mapa se escriben en la VRAM como
las escribe el GS (PSMCT32) y luego cada textura que usan las piezas se lee con su
formato (PSMT4 / PSMT8 / PSMCT32) y su paleta (CLUT).

Uso:
    python kf4_tex.py 031.map            -> carpeta 031_tex/ con un PNG por textura
    python kf4_tex.py 031.map --vram     -> además vram.png (la VRAM entera como 32 bits)

También se usa como módulo desde los otros scripts (load_map_textures).
Requiere numpy y Pillow (pip install numpy pillow).
"""

import os
import sys
import struct
import numpy as np

VRAM_BYTES = 4 * 1024 * 1024

# ---------- tablas del GS (iguales que ToolsForKFIV/Texture.cs) ----------
BLOCK32 = np.array([0, 1, 4, 5, 16, 17, 20, 21, 2, 3, 6, 7, 18, 19, 22, 23,
                    8, 9, 12, 13, 24, 25, 28, 29, 10, 11, 14, 15, 26, 27, 30, 31])
BLOCK8 = BLOCK32
BLOCK4 = np.array([0, 2, 8, 10, 1, 3, 9, 11, 4, 6, 12, 14, 5, 7, 13, 15,
                   16, 18, 24, 26, 17, 19, 25, 27, 20, 22, 28, 30, 21, 23, 29, 31])
COLW32 = np.array([0, 1, 4, 5, 8, 9, 12, 13, 2, 3, 6, 7, 10, 11, 14, 15])
_c8a = [0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13,
        2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15,
        8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5,
        10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7]
_c8b = _c8a[32:] + _c8a[:32]
COLW8 = np.array([_c8a, _c8b])
_c4a = ([0, 1, 4, 5, 8, 9, 12, 13] * 4 + [2, 3, 6, 7, 10, 11, 14, 15] * 4 +
        [8, 9, 12, 13, 0, 1, 4, 5] * 4 + [10, 11, 14, 15, 2, 3, 6, 7] * 4)
_c4b = _c4a[64:] + _c4a[:64]
COLW4 = np.array([_c4a, _c4b])
COLB8 = np.array([0] * 8 + [2] * 8 + [0] * 8 + [2] * 8 + [1] * 8 + [3] * 8 + [1] * 8 + [3] * 8)
COLB4 = np.array(([0] * 8 + [2] * 8 + [4] * 8 + [6] * 8) * 2 + ([1] * 8 + [3] * 8 + [5] * 8 + [7] * 8) * 2)


def addr32(bp, bw, x, y):
    """Índice de byte en la VRAM del píxel (x, y) en PSMCT32."""
    page = x // 64 + (y // 32) * bw
    px, py = x % 64, y % 32
    block = BLOCK32[px // 8 + (py // 8) * 8]
    bx, by = px % 8, py % 8
    col = by // 2
    cw = COLW32[bx + (by % 2) * 8]
    return bp * 256 + ((page * 2048 + block * 64 + col * 16 + cw) * 4)


def read8(vram, bp, bw, w, h):
    y, x = np.mgrid[0:h, 0:w]
    bw2 = max(1, bw >> 1)
    page = x // 128 + (y // 64) * bw2
    px, py = x % 128, y % 64
    block = BLOCK8[px // 16 + (py // 16) * 8]
    bx, by = px % 16, py % 16
    col = by // 4
    cy = by % 4
    cw = COLW8[col & 1, bx + cy * 16]
    cb = COLB8[bx + cy * 16]
    a = bp * 256 + ((page * 2048 + block * 64 + col * 16 + cw) * 4) + cb
    return vram[a % VRAM_BYTES]


def read4(vram, bp, bw, w, h):
    y, x = np.mgrid[0:h, 0:w]
    bw2 = max(1, bw >> 1)
    page = x // 128 + (y // 128) * bw2
    px, py = x % 128, y % 128
    block = BLOCK4[px // 32 + (py // 16) * 4]
    bx, by = px % 32, py % 16
    col = by // 4
    cy = by % 4
    cw = COLW4[col & 1, bx + cy * 32]
    cb = COLB4[bx + cy * 32]
    a = bp * 256 + ((page * 2048 + block * 64 + col * 16 + cw) * 4) + (cb >> 1)
    byte = vram[a % VRAM_BYTES]
    return np.where(cb & 1, byte >> 4, byte & 0xF)


def read32(vram, bp, bw, w, h):
    y, x = np.mgrid[0:h, 0:w]
    a = addr32(bp, max(1, bw), x, y)
    out = np.stack([vram[(a + k) % VRAM_BYTES] for k in range(4)], -1)
    return out  # R, G, B, A (PS2 guarda RGBA en ese orden en PSMCT32)


def write32(vram, bp, bw, sx, sy, w, h, data):
    y, x = np.mgrid[sy:sy + h, sx:sx + w]
    a = addr32(bp, max(1, bw), x, y).reshape(-1)
    px = np.frombuffer(data[:w * h * 4], dtype=np.uint8)
    if len(px) < w * h * 4:
        px = np.concatenate([px, np.zeros(w * h * 4 - len(px), np.uint8)])
    px = px.reshape(-1, 4)
    for k in range(4):
        vram[(a + k) % VRAM_BYTES] = px[:, k]


def alpha_fix(rgba):
    rgba = rgba.copy()
    rgba[..., 3] = np.minimum(rgba[..., 3].astype(np.int32) * 2, 255).astype(np.uint8)
    return rgba


def read_clut(vram, cbp, psm):
    """CSM1. 4 bpp: 8x2 colores; 8 bpp: 16x16 con el cambio 8-15 <-> 16-23 en cada grupo de 32."""
    if psm == 0x14:
        c = read32(vram, cbp, 1, 8, 2).reshape(16, 4)
    else:
        c = read32(vram, cbp, 1, 16, 16).reshape(256, 4)
        idx = np.arange(256)
        sw = idx.copy()
        m1 = (idx & 0x18) == 0x08
        m2 = (idx & 0x18) == 0x10
        sw[m1] += 8
        sw[m2] -= 8
        c = c[sw]
    return alpha_fix(c)


# ---------- bloque de texturas del mapa ----------
def upload_map_textures(d, off_tex, off_end, log=None):
    """Recorre las subidas GIF del bloque de texturas y las escribe en una VRAM emulada."""
    vram = np.zeros(VRAM_BYTES, np.uint8)
    pos = off_tex
    uploads = []
    while pos + 16 <= off_end:
        qw = struct.unpack_from("<I", d, pos)[0]
        length = (qw - 7) * 16
        if qw == 0 or length < 0:
            pos += 16
            continue
        bitblt = struct.unpack_from("<Q", d, pos + 48)[0]
        trxpos = struct.unpack_from("<Q", d, pos + 64)[0]
        trxreg = struct.unpack_from("<Q", d, pos + 80)[0]
        dbp = (bitblt >> 32) & 0x3FFF
        dbw = (bitblt >> 48) & 0x3F
        dpsm = (bitblt >> 56) & 0x3F
        dsax = (trxpos >> 32) & 0x7FF
        dsay = (trxpos >> 48) & 0x7FF
        rrw = trxreg & 0xFFF
        rrh = (trxreg >> 32) & 0xFFF
        data = d[pos + 128:pos + 128 + length]
        if dpsm != 0 and log is not None:
            log.append(f"subida en 0x{pos:X} con DPSM {dpsm} (se trata como 32 bits)")
        if rrw and rrh and rrw <= 2048 and rrh <= 2048:
            write32(vram, dbp, dbw, dsax, dsay, rrw, rrh, data)
            uploads.append({"offset": pos, "qw": qw, "dbp": dbp, "dbw": dbw, "dpsm": dpsm,
                            "x": dsax, "y": dsay, "w": rrw, "h": rrh, "bytes": length})
        elif log is not None:
            log.append(f"subida rara en 0x{pos:X}: {rrw}x{rrh}")
        pos += 128 + length
    return vram, uploads


def decode_texture(vram, tex):
    """tex: dict con TBP, TBW, PSM, CBP, W, H -> array RGBA (H, W, 4)."""
    psm, w, h = tex["PSM"], tex["W"], tex["H"]
    if psm == 0x14:
        idx = read4(vram, tex["TBP"], tex["TBW"], w, h)
        return read_clut(vram, tex["CBP"], psm)[idx]
    if psm == 0x13:
        idx = read8(vram, tex["TBP"], tex["TBW"], w, h)
        return read_clut(vram, tex["CBP"], psm)[idx]
    if psm == 0x00:
        return alpha_fix(read32(vram, tex["TBP"], tex["TBW"], w, h))
    return None


def tex0_fields(v):
    return {"TBP": v & 0x3FFF, "TBW": (v >> 14) & 0x3F, "PSM": (v >> 20) & 0x3F,
            "W": 1 << ((v >> 26) & 0xF), "H": 1 << ((v >> 30) & 0xF),
            "TCC": (v >> 34) & 1, "CBP": (v >> 37) & 0x3FFF}


def piece_textures(d, log=None):
    """Lista de TEX0 distintos que usan las piezas del mapa (recorre los OMD de los registros)."""
    off_models = struct.unpack_from("<I", d, 0x04)[0]
    count = struct.unpack_from("<H", d, 0x2C)[0]
    seen = {}
    pos = off_models
    for _ in range(count):
        length, nmesh = struct.unpack_from("<IH", d, pos)
        if length <= 0:
            break
        for mi in range(nmesh):
            mo = pos + 0x10 + mi * 48
            off_ts, n_ts = struct.unpack_from("<II", d, mo + 36)
            p = pos + off_ts
            for _ in range(n_ts):
                tex0 = struct.unpack_from("<Q", d, p + 0x40)[0]
                nv = d[p + 0x70]
                f = tex0_fields(tex0)
                key = (f["TBP"], f["CBP"], f["PSM"], f["W"], f["H"], f["TBW"])
                seen.setdefault(key, f)
                p += 0x90 + nv * 32 + 16
        pos += length
    return list(seen.values())


def tex_name(f):
    psm = {0x14: "4", 0x13: "8", 0x00: "32"}.get(f["PSM"], str(f["PSM"]))
    return f"TBP{f['TBP']:04X}_CBP{f['CBP']:04X}_{psm}bpp_{f['W']}x{f['H']}"


def load_map_textures(d, log=None):
    off_tex = struct.unpack_from("<I", d, 0x24)[0]
    off_end = struct.unpack_from("<I", d, 0x28)[0]
    vram, uploads = upload_map_textures(d, off_tex, off_end, log)
    out = {}
    for f in piece_textures(d, log):
        img = decode_texture(vram, f)
        if img is not None:
            out[(f["TBP"], f["CBP"], f["PSM"], f["W"], f["H"])] = (f, img)
    return out, vram, uploads


def main():
    from PIL import Image
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    d = open(path, "rb").read()
    log = []
    texs, vram, uploads = load_map_textures(d, log)
    base = os.path.splitext(os.path.basename(path))[0]
    outdir = os.path.join(os.path.dirname(os.path.abspath(path)), base + "_tex")
    os.makedirs(outdir, exist_ok=True)
    for key, (f, img) in texs.items():
        Image.fromarray(img, "RGBA").save(os.path.join(outdir, tex_name(f) + ".png"))
    if "--vram" in sys.argv:
        v = read32(vram, 0, 16, 1024, 1024)
        Image.fromarray(alpha_fix(v), "RGBA").convert("RGB").save(os.path.join(outdir, "vram.png"))
    with open(os.path.join(outdir, "subidas.txt"), "w", encoding="utf-8") as o:
        for u in uploads:
            o.write(f"0x{u['offset']:08X} DBP {u['dbp']:04X} DBW {u['dbw']:2} PSM {u['dpsm']} "
                    f"{u['w']}x{u['h']} en ({u['x']},{u['y']}) {u['bytes']} bytes\n")
        o.write("\n".join(log))
    print(f"{len(uploads)} subidas, {len(texs)} texturas -> {outdir}")


if __name__ == "__main__":
    main()
