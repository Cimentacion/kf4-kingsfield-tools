#!/usr/bin/env python3
"""
kf4_view.py - Exporta un mapa de King's Field IV a OBJ + MTL + PNG con sus texturas reales,
listo para Blender 2.79 (File > Import > Wavefront .obj), y opcionalmente lo renderiza.

Uso:
    python kf4_view.py 031.map                 -> 031_obj/031.obj + .mtl + texturas
    python kf4_view.py 031.map --render X Y Z YAW PITCH   -> además 031_render.png desde ese punto
                                                 (coordenadas de Blender, metros; ángulos en grados)

Las piezas se colocan con su transformación del mapa. Ejes de Blender (Z arriba), escala 1/100
(1 unidad = 1 metro aprox.). El color de vértice (luz horneada) se guarda en el nombre del
material no; va en un .ply aparte si se quiere (kf4_mapdump). Requiere numpy y Pillow.
"""

import os
import sys
import math
import struct
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kf4_mapdump as md   # noqa: E402
import kf4_tex as kt       # noqa: E402


def map_triangles(d):
    """Triángulos del mapa en coordenadas de Blender: lista de (3 pos, 3 uv, 3 color, clave textura)."""
    log = []
    n_rec = struct.unpack_from("<H", d, 0x3C)[0]
    recs = []
    for i in range(n_rec):
        o = md.OFF_RECORDS + i * md.REC
        recs.append({"pos": md.f32(d, o, 3), "rot": md.f32(d, o + 0x10, 3), "scale": md.f32(d, o + 0x20, 3),
                     "omd": md.s16(d, o + 0x30)})
    off_models = struct.unpack_from("<I", d, 0x04)[0]
    n_models = struct.unpack_from("<H", d, 0x2C)[0]
    omds = md.walk_omds(d, off_models, n_models, True, log, "mapa")
    tris = []
    for r in recs:
        if r["omd"] < 0 or r["omd"] >= len(omds):
            continue
        p, ro, s = md.to_gl_trs(r["pos"], r["rot"], r["scale"])
        m = md.mat_trs(p, ro, s)
        for (a, b, c, tbp, cbp) in omds[r["omd"]][1]:
            P, U, C = [], [], []
            for (g, uv, col) in (a, b, c):
                x, y, z = md.mat_apply(m, g)
                P.append((x / 100.0, -z / 100.0, y / 100.0))
                U.append(uv)
                C.append(col[:3])
            tris.append((P, U, C, (tbp, cbp)))
    return tris, log


def texture_lookup(texs):
    """Clave (TBP, CBP) -> imagen RGBA."""
    out = {}
    for key, (f, img) in texs.items():
        out[(f["TBP"], f["CBP"])] = (f, img)
    return out


def export_obj(name, tris, texs, outdir):
    os.makedirs(outdir, exist_ok=True)
    look = texture_lookup(texs)
    mats = {}
    for k, (f, img) in look.items():
        fn = kt.tex_name(f) + ".png"
        Image.fromarray(img, "RGBA").save(os.path.join(outdir, fn))
        mats[k] = (kt.tex_name(f), fn)
    by_mat = {}
    for t in tris:
        by_mat.setdefault(t[3], []).append(t)
    with open(os.path.join(outdir, name + ".mtl"), "w") as m:
        for k, (mn, fn) in mats.items():
            m.write(f"newmtl {mn}\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nillum 1\nmap_Kd {fn}\n\n")
        m.write("newmtl sin_textura\nKd 0.5 0.5 0.5\n\n")
    with open(os.path.join(outdir, name + ".obj"), "w") as o:
        o.write(f"# King's Field IV {name}.map - exportado por kf4_view.py\nmtllib {name}.mtl\n")
        vi = 1
        for k, ts in by_mat.items():
            o.write(f"usemtl {mats[k][0] if k in mats else 'sin_textura'}\n")
            for (P, U, C, _) in ts:
                for (x, y, z), (u, v) in zip(P, U):
                    o.write(f"v {x:.4f} {y:.4f} {z:.4f}\nvt {u:.5f} {1.0 - v:.5f}\n")
                o.write(f"f {vi}/{vi} {vi + 1}/{vi + 1} {vi + 2}/{vi + 2}\n")
                vi += 3
    return len(tris)


def render(tris, texs, eye, yaw, pitch, W=640, H=480, fov=70, fog=(0, 0, 0), fog_near=40, fog_far=220, out="r.png"):
    look = texture_lookup(texs)
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    fwd = np.array([cy * cp, sy * cp, sp])
    right = np.cross(fwd, [0, 0, 1.0]); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    R = np.stack([right, up, fwd])
    eye = np.array(eye, float)
    fl = (W / 2) / math.tan(math.radians(fov) / 2)
    img = np.zeros((H, W, 3)); img[:] = fog
    zb = np.full((H, W), np.inf)
    NEAR = 0.15

    def clip_near(Q, Ua, Ca):
        """Recorta el triángulo contra el plano cercano; devuelve triángulos (Q, U, C)."""
        pts = list(zip(Q, Ua, Ca))
        out = []
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            ina, inb = a[0][2] >= NEAR, b[0][2] >= NEAR
            if ina:
                out.append(a)
            if ina != inb:
                t = (NEAR - a[0][2]) / (b[0][2] - a[0][2])
                out.append(tuple(a[k] + (b[k] - a[k]) * t for k in range(3)))
        return [(np.array([out[0][0], out[i][0], out[i + 1][0]]), np.array([out[0][1], out[i][1], out[i + 1][1]]),
                 np.array([out[0][2], out[i][2], out[i + 1][2]])) for i in range(1, len(out) - 1)]

    work = []
    for (P, U, C, key) in tris:
        Q = (np.array(P) - eye) @ R.T
        if (Q[:, 2] < NEAR).all():
            continue
        Ua = np.array(U, float)
        Ca = np.array(C, float)
        if (Q[:, 2] < NEAR).any():
            for q, u, c in clip_near(Q, Ua, Ca):
                work.append((q, u, c, key))
        else:
            work.append((Q, Ua, Ca, key))
    for (Q, Ua, Ca, key) in work:
        sx = W / 2 + fl * Q[:, 0] / Q[:, 2]
        syy = H / 2 - fl * Q[:, 1] / Q[:, 2]
        x0, x1 = int(max(0, sx.min())), int(min(W - 1, sx.max()))
        y0, y1 = int(max(0, syy.min())), int(min(H - 1, syy.max()))
        if x0 > x1 or y0 > y1:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        (ax, bx, cx), (ay, by, cyy) = sx, syy
        den = (by - cyy) * (ax - cx) + (cx - bx) * (ay - cyy)
        if abs(den) < 1e-9:
            continue
        w0 = ((by - cyy) * (xs - cx) + (cx - bx) * (ys - cyy)) / den
        w1 = ((cyy - ay) * (xs - cx) + (ax - cx) * (ys - cyy)) / den
        w2 = 1 - w0 - w1
        msk = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not msk.any():
            continue
        iz = w0 / Q[0, 2] + w1 / Q[1, 2] + w2 / Q[2, 2]
        z = 1.0 / iz
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        msk &= z < sub
        if not msk.any():
            continue
        u = (w0 * Ua[0, 0] / Q[0, 2] + w1 * Ua[1, 0] / Q[1, 2] + w2 * Ua[2, 0] / Q[2, 2]) * z
        v = (w0 * Ua[0, 1] / Q[0, 2] + w1 * Ua[1, 1] / Q[1, 2] + w2 * Ua[2, 1] / Q[2, 2]) * z
        vc = (w0[..., None] * Ca[0] / Q[0, 2] + w1[..., None] * Ca[1] / Q[1, 2] + w2[..., None] * Ca[2] / Q[2, 2]) * z[..., None]
        if key in look:
            t = look[key][1]
            th, tw = t.shape[:2]
            tx = (np.floor(u * tw).astype(int)) % tw
            ty = (np.floor(v * th).astype(int)) % th
            texel = t[ty, tx]
            msk &= texel[..., 3] > 40
            col = texel[..., :3] * vc / 128.0
        else:
            col = vc * 2
        k = np.clip((z - fog_near) / (fog_far - fog_near), 0, 1)[..., None]
        col = col * (1 - k) + np.array(fog) * k
        sub[msk] = z[msk]
        img[y0:y1 + 1, x0:x1 + 1][msk] = col[msk]
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(out)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    d = open(path, "rb").read()
    name = os.path.splitext(os.path.basename(path))[0]
    texs, _, _ = kt.load_map_textures(d)
    tris, log = map_triangles(d)
    outdir = os.path.join(os.path.dirname(os.path.abspath(path)), name + "_obj")
    n = export_obj(name, tris, texs, outdir)
    print(f"{n} triángulos, {len(texs)} texturas -> {outdir}")
    if "--render" in sys.argv:
        i = sys.argv.index("--render")
        x, y, z, yaw, pitch = map(float, sys.argv[i + 1:i + 6])
        out = os.path.join(os.path.dirname(os.path.abspath(path)), f"{name}_render.png")
        render(tris, texs, (x, y, z), yaw, pitch, out=out)
        print("render ->", out)


if __name__ == "__main__":
    main()
