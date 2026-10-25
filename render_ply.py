"""Rasterizador simple de los PLY de kf4_mapdump (vertex colors, z-buffer, niebla). Solo para inspección."""
import sys, struct, math
import numpy as np
from PIL import Image


def load(path):
    d = open(path, "rb").read()
    end = d.index(b"end_header\n") + 11
    hdr = d[:end].decode()
    nv = int(hdr.split("element vertex ")[1].split()[0])
    nf = int(hdr.split("element face ")[1].split()[0])
    V = np.frombuffer(d, dtype=np.dtype([("p", "<f4", 3), ("uv", "<f4", 2), ("c", "u1", 4)]), count=nv, offset=end)
    F = np.frombuffer(d, dtype=np.dtype([("n", "u1"), ("i", "<i4", 3)]), count=nf, offset=end + nv * 24)
    return V["p"].astype(np.float64), V["c"][:, :3].astype(np.float64), F["i"]


def look(eye, target):
    f = np.array(target, float) - eye
    f /= np.linalg.norm(f)
    up = np.array([0, 0, 1.0])
    r = np.cross(f, up); r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return np.stack([r, u, f])


def render(P, C, F, eye, target, W=640, H=480, fov=60, fog=None, out="o.png"):
    R = look(np.array(eye, float), target)
    Q = (P - eye) @ R.T
    fl = (W / 2) / math.tan(math.radians(fov) / 2)
    img = np.zeros((H, W, 3)); zb = np.full((H, W), np.inf)
    if fog is not None:
        img[:] = fog
    tri = Q[F]; col = C[F]
    zmin = tri[:, :, 2].min(1)
    keep = zmin > 0.3
    tri, col = tri[keep], col[keep]
    sx = W / 2 + fl * tri[:, :, 0] / tri[:, :, 2]
    sy = H / 2 - fl * tri[:, :, 1] / tri[:, :, 2]
    for t in range(len(tri)):
        x0, x1 = int(max(0, sx[t].min())), int(min(W - 1, sx[t].max()))
        y0, y1 = int(max(0, sy[t].min())), int(min(H - 1, sy[t].max()))
        if x0 > x1 or y0 > y1 or (x1 - x0) * (y1 - y0) > W * H:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        (ax, bx, cx), (ay, by, cy) = sx[t], sy[t]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        w0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        w1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        w2 = 1 - w0 - w1
        m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not m.any():
            continue
        z = w0 * tri[t, 0, 2] + w1 * tri[t, 1, 2] + w2 * tri[t, 2, 2]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        m &= z < sub
        if not m.any():
            continue
        sub[m] = z[m]
        c = w0[..., None] * col[t, 0] + w1[..., None] * col[t, 1] + w2[..., None] * col[t, 2]
        if fog is not None:
            k = np.clip((z - fog_near) / (fog_far - fog_near), 0, 1)[..., None]
            c = c * (1 - k) + np.array(fog) * k
        img[y0:y1 + 1, x0:x1 + 1][m] = c[m]
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(out)


fog_near, fog_far = 30.0, 160.0
if __name__ == "__main__":
    P, C, F = load(sys.argv[1])
    print("bbox", P.min(0).round(1), P.max(0).round(1), "tris", len(F))
