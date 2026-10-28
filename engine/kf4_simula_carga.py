"""Simulador de la carga sin fundido del King's Field IV (MapLoad_Update, Map_MakeCurrent, la lista de dibujo con
los bloques de flags) sobre los mapas generados, andando por los niveles, comparado con el nivel entero.
Uso: python sim.py carpeta_mapas ultimo.pkl full0.map full1.map salida_dir [retardo_casillas]"""
import sys, os, math, struct, pickle, collections, json
sys.path.insert(0, '/home/claude/kf4')
import numpy as np
import kf4_mapdump as md, kf4_view as kv, kf4_tex as kt_, kf4_trozos as kt

carpeta, ult, f0, f1, sal = sys.argv[1:6]
RETARDO = float(sys.argv[6]) if len(sys.argv) > 6 else 3.0      # casillas andadas mientras carga un mapa
os.makedirs(sal, exist_ok=True)
U = pickle.load(open(ult, 'rb'))
D = U['D']; OFF = U['off']


def ed2F(lv, p):
    o = OFF[lv]
    return (p[0] + o[0] / 100, p[1] + o[2] / 100, p[2] - o[1] / 100)


class Mapa:
    def __init__(self, path, tag):
        d = open(path, 'rb').read()
        self.tag = tag
        nrec, nfb = struct.unpack_from('<2H', d, 0x3C)
        self.recs = []
        for i in range(nrec):
            o = md.OFF_RECORDS + i * 0x80
            self.recs.append(dict(pos=md.f32(d, o, 3), rot=md.f32(d, o + 0x10, 3), sc=md.f32(d, o + 0x20, 3),
                                  omd=md.s16(d, o + 0x30), csk=md.s16(d, o + 0x32), g=d[o + 0x38], needs=d[o + 0x39],
                                  ori=d[o + 0x3A], flags=struct.unpack_from('<I', d, o + 0x3C)[0]))
        p = md.OFF_RECORDS + nrec * 0x80
        self.bloques = []
        for b in range(nfb):
            blk = d[p + b * 0x40:p + (b + 1) * 0x40]
            bits = {i for i in range(256) if blk[i // 8] >> (i % 8) & 1}
            pares = {(blk[0x20 + i], blk[0x30 + i]) for i in range(16)}
            self.bloques.append((bits, pares))
        p += nfb * 0x40
        self.neigh = [struct.unpack_from('<3fHH', d, p + i * 16) for i in range(32)]
        # triángulos de dibujo por registro (marco F: m, z arriba)
        off_models = struct.unpack_from('<I', d, 0x04)[0]
        nm = struct.unpack_from('<H', d, 0x2C)[0]
        omds = md.walk_omds(d, off_models, nm, True, [], 'm')
        self.tris = []      # (registro, array 3x3)
        for ri, r in enumerate(self.recs):
            if r['omd'] < 0 or r['omd'] >= len(omds):
                continue
            pp, ro, s = md.to_gl_trs(r['pos'], r['rot'], r['sc'])
            m = md.mat_trs(pp, ro, s)
            for (a, b, c, tbp, cbp) in omds[r['omd']][1]:
                P = []
                for (g, uv, col) in (a, b, c):
                    x, y, z = md.mat_apply(m, g)
                    P.append((x / 100.0, -z / 100.0, y / 100.0))
                self.tris.append((ri, P))
        self.tri_rec = np.array([t[0] for t in self.tris], dtype=np.int32)
        self.tri_v = np.array([t[1] for t in self.tris], dtype=np.float32).reshape(-1, 3, 3)
        # suelos de la colisión por registro (marco F)
        off_c = struct.unpack_from('<I', d, 0x08)[0]
        nc = struct.unpack_from('<H', d, 0x2E)[0]
        csks, q = [], off_c
        for _ in range(nc):
            size = struct.unpack_from('<I', d, q + 0x14)[0]
            csks.append(q)
            q += size
        self.suelos = []    # (registro, tri F)
        for ri, r in enumerate(self.recs):
            if r['csk'] < 0 or r['csk'] >= len(csks):
                continue
            q = csks[r['csk']]
            pts_off, npts = struct.unpack_from('<2I', d, q + 8)
            off_f = struct.unpack_from('<I', d, q + 0x18 + 4)[0]
            cnt_f = struct.unpack_from('<H', d, q + 0x38 + 2)[0]
            pts = [md.f32(d, q + pts_off + i * 16, 3) for i in range(npts)]
            ox, oy, oz = r['pos']
            pp = q + off_f
            for _ in range(cnt_f):
                n = struct.unpack_from('<H', d, pp)[0]
                ids = [struct.unpack_from('<I', d, pp + 0x20 + i * 16)[0] for i in range(n)]
                pp += 0x20 + n * 16
                for i in range(n - 2):
                    tri = []
                    for k in ids[i:i + 3]:
                        x, y, z = pts[k]
                        tri.append(((x + ox) / 100, (z + oz) / 100, -(y + oy) / 100))
                    self.suelos.append((ri, tri))


def suelo_bajo(mapa, shift, p, zmax=1.6):
    """(registro, altura) del suelo del mapa (desplazado shift) bajo el punto p, el más cercano a su altura."""
    mejor = None
    for ri, (a, b, c) in mapa.suelos:
        a = (a[0] + shift[0], a[1] + shift[1], a[2] + shift[2]); b = (b[0] + shift[0], b[1] + shift[1], b[2] + shift[2])
        c = (c[0] + shift[0], c[1] + shift[1], c[2] + shift[2])
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-9:
            continue
        w0 = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / den
        w1 = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / den
        w2 = 1 - w0 - w1
        if min(w0, w1, w2) < -1e-4:
            continue
        z = w0 * a[2] + w1 * b[2] + w2 * c[2]
        if abs(z - p[2]) <= zmax and (mejor is None or abs(z - p[2]) < abs(mejor[1] - p[2])):
            mejor = (ri, z)
    return mejor


def profundidad(tv, eye, yaw, W=160, H=120, fov=70, lejos=45.0):
    """Mapa de profundidad (m) de los triángulos tv (N,3,3)."""
    zb = np.full((H, W), np.inf)
    if len(tv) == 0:
        return zb
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    fwd = np.array([cy, sy, 0.0]); right = np.array([sy, -cy, 0.0]); up = np.array([0, 0, 1.0])
    R = np.stack([right, up, fwd])
    Q = (tv - np.array(eye)) @ R.T                      # (N,3,3) cámara
    cen = Q.mean(axis=1)
    keep = (Q[:, :, 2].max(axis=1) > 0.15) & (np.linalg.norm(cen, axis=1) < lejos + 10)
    Q = Q[keep]
    fl = (W / 2) / math.tan(math.radians(fov) / 2)
    for T in Q:
        if (T[:, 2] < 0.15).any():
            # recorte simple: los que cruzan el plano cercano se ignoran si están muy cerca (paredes junto a la cámara)
            pts = [t for t in T if t[2] >= 0.15]
            if len(pts) < 3:
                continue
            T = np.array(pts[:3])
        sx = W / 2 + fl * T[:, 0] / T[:, 2]; syy = H / 2 - fl * T[:, 1] / T[:, 2]
        x0, x1 = int(max(0, sx.min())), int(min(W - 1, sx.max()))
        y0, y1 = int(max(0, syy.min())), int(min(H - 1, syy.max()))
        if x0 > x1 or y0 > y1:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        (ax, bx, cx), (ay, by, cc) = sx, syy
        den = (by - cc) * (ax - cx) + (cx - bx) * (ay - cc)
        if abs(den) < 1e-9:
            continue
        w0 = ((by - cc) * (xs - cx) + (cx - bx) * (ys - cc)) / den
        w1 = ((cc - ay) * (xs - cx) + (ax - cx) * (ys - cc)) / den
        w2 = 1 - w0 - w1
        msk = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not msk.any():
            continue
        z = 1.0 / (w0 / T[0, 2] + w1 / T[1, 2] + w2 / T[2, 2])
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        m2 = msk & (z < sub)
        sub[m2] = z[m2]
    return zb


# ---- los mapas ----
trozos = U['trozos']
mapas = {}
for lv, num, cel, nom in trozos:
    mapas[num] = Mapa(os.path.join(carpeta, f'{num:03d}.map'), num)
    mapas[num].nivel = lv
    mapas[num].nombre = nom
full = {0: Mapa(f0, 99), 1: Mapa(f1, 37)}
print('mapas cargados', len(mapas))

# ---- el camino: por las casillas de suelo de los dos niveles (el pasillo del enlace une el 0 con el 1) ----
H = U['H']; M = U['M']
dx, dy = round(D[0] / 2.5), round(D[1] / 2.5)
def nodos_vecinos(n):
    lv, c = n
    out = []
    for k in kt.VECINAS4:
        m = (c[0] + k[0], c[1] + k[1])
        if m in H[lv] and kt._pasa(H[lv][c], H[lv][m]):
            out.append((lv, m))
    if lv == 0 and c in M:
        out.append((1, (c[0] + dx, c[1] + dy)))
    if lv == 1 and (c[0] - dx, c[1] - dy) in M:
        out.append((0, (c[0] - dx, c[1] - dy)))
    return out
def camino(a, b):
    prev = {a: None}; fr = [a]
    while fr:
        sig = []
        for n in fr:
            if n == b:
                fr = []; break
            for m in nodos_vecinos(n):
                if m not in prev:
                    prev[m] = n; sig.append(m)
        else:
            fr = sig
            continue
        break
    if b not in prev:
        return None
    out = [b]
    while prev[out[-1]] is not None:
        out.append(prev[out[-1]])
    return out[::-1]
inicio = (0, kt.celda(U['inicio']))
# visita: el centro de cada trozo (de cada nivel), en orden
objetivos = []
for lv, num, cel, nom in trozos:
    cs = [c for c in cel if c in H[lv]]
    if not cs:
        continue
    cx = sum(c[0] for c in cs) / len(cs); cy = sum(c[1] for c in cs) / len(cs)
    objetivos.append(((lv, min(cs, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)), nom))
ruta = [inicio]
for obj, nom in objetivos:
    cam = camino(ruta[-1], obj)
    if cam:
        ruta += cam[1:]
GUARDAR = set()
paso = int(sys.argv[7]) if len(sys.argv) > 7 else 2
print('ruta', len(ruta), 'casillas')

# ---- la simulación ----
def pos_F(n, z):
    lv, c = n
    return ed2F(lv, ((c[0] + 0.5) * 2.5, (c[1] + 0.5) * 2.5, z))
def a_marco(p, de_lv, a_lv):
    """F del nivel de_lv -> F del nivel a_lv."""
    if de_lv == a_lv:
        return p
    e = (p[0] - OFF[de_lv][0] / 100, p[1] - OFF[de_lv][2] / 100, p[2] + OFF[de_lv][1] / 100)
    e = (e[0] - D[0], e[1] - D[1], e[2] - D[2]) if de_lv == 1 else (e[0] + D[0], e[1] + D[1], e[2] + D[2])
    return ed2F(a_lv, e)

actual = mapas[99]
otro = None            # (mapa, desfase F)
cargando = None        # (mapa, desfase F, casillas que faltan)
z = max(H[0][inicio[1]])
informe = []
peores = []
anterior = None
for i, n in enumerate(ruta):
    lv, c = n
    zs = H[lv][c]
    z = min(zs, key=lambda q: abs(q - z))
    pF = a_marco(pos_F(n, z), lv, actual.nivel)
    # el suelo que pisa: del mapa actual o del otro
    s_act = suelo_bajo(actual, (0, 0, 0), pF)
    s_otr = suelo_bajo(otro[0], otro[1], pF) if otro else None
    if s_otr and (not s_act or abs(s_otr[1] - pF[2]) < abs(s_act[1] - pF[2]) - 0.01):
        # Map_MakeCurrent: el otro pasa a ser el actual
        nm, sh = otro
        otro = (actual, (-sh[0], -sh[1], -sh[2]))
        actual = nm
        pF = (pF[0] - sh[0], pF[1] - sh[1], pF[2] - sh[2])
        s_act = s_otr
        cargando = None
    if not s_act:
        informe.append((i, 'SIN SUELO', actual.tag))
        continue
    rec = actual.recs[s_act[0]]
    # MapLoad_Update: pedir el vecino de este registro (al empezar a cargar, el hueco del otro se vacía)
    if rec['ori'] != 0xFF:
        x, y, zz, mp, _ = actual.neigh[rec['ori']]
        sh = (-x / 100, -zz / 100, y / 100)
        if mp != actual.tag and (otro is None or otro[0].tag != mp) and (cargando is None or cargando[0].tag != mp):
            cargando = [mapas[mp], sh, RETARDO]
            otro = None
            informe.append((i, 'CARGA', mp))
        if rec['needs'] and cargando is not None:
            informe.append((i, 'ESPERA', cargando[0].tag))
            cargando[2] = 0
    if cargando is not None:
        if cargando[2] <= 0:
            otro = (cargando[0], cargando[1])
            cargando = None
        else:
            cargando[2] -= 1
    if i % paso:
        continue
    # lo que dibuja el juego
    bits, pares = actual.bloques[rec['g']] if rec['g'] < len(actual.bloques) else (set(range(256)), set())
    sel = np.array([bool(actual.recs[r]['g'] in bits or actual.recs[r]['flags'] & 0x80000000) for r in actual.tri_rec], dtype=bool)
    tv = [actual.tri_v[sel]]
    if otro:
        om, sh = otro
        sel2 = np.array([(om.tag, om.recs[r]['g']) in pares for r in om.tri_rec])
        tv.append(om.tri_v[sel2] + np.array(sh, dtype=np.float32))
    tv = np.concatenate(tv) if tv else np.zeros((0, 3, 3))
    # el nivel entero, en el marco del actual
    ref = full[lv].tri_v
    if lv != actual.nivel:
        o = np.array(a_marco((0, 0, 0), lv, actual.nivel)) - np.array(a_marco((0, 0, 0), lv, lv))
        ref = ref + o.astype(np.float32)
    sig = ruta[min(len(ruta) - 1, i + 3)]
    pS = a_marco(pos_F(sig, z), sig[0], actual.nivel)
    yaw = math.degrees(math.atan2(pS[1] - pF[1], pS[0] - pF[0])) if (pS[0], pS[1]) != (pF[0], pF[1]) else 0
    eye = (pF[0], pF[1], pF[2] + 1.6)
    zr = profundidad(ref, eye, yaw)
    zs_ = profundidad(tv, eye, yaw)
    lejos = float(os.environ.get('LEJOS', '30'))
    hueco = (zr < lejos) & (zs_ > zr + 1.5)
    pct = hueco.mean() * 100
    if pct > 20 or i in GUARDAR:
        from PIL import Image
        def gris(zb):
            g = np.where(np.isinf(zb), 0, np.clip(255 - zb * 6, 30, 255))
            return g.astype(np.uint8)
        im = np.concatenate([gris(zr), np.full((120, 4), 255, np.uint8), gris(zs_)], axis=1)
        rgb = np.stack([im] * 3, -1)
        rgb[:, 164:][hueco] = (255, 0, 0)
        Image.fromarray(rgb).resize((648, 240), Image.NEAREST).save(os.path.join(sal, f'f{i:04d}.png'))
    informe.append((i, f'{pct:.1f}% huecos', actual.tag, otro[0].tag if otro else None, rec['g']))
    peores.append((pct, i, eye, yaw, lv, actual.tag, otro[0].tag if otro else None))
    print(i, n, f'{pct:.1f}%', 'actual', actual.tag, 'otro', otro[0].tag if otro else None, 'grupo', rec['g'], flush=True)
json.dump([list(map(str, x)) for x in informe], open(os.path.join(sal, 'informe.json'), 'w'))
pickle.dump(peores, open(os.path.join(sal, 'peores.pkl'), 'wb'))
peores.sort(reverse=True)
print('PEORES', [(round(p[0], 1), p[1], p[5], p[6]) for p in peores[:15]])
print('MEDIA', sum(p[0] for p in peores) / max(1, len(peores)))
