#!/usr/bin/env python3
"""
kf4_editor_local.py - Field4Editor (el editor de mapas) en tu PC, conectado a tu ISO de King's Field IV.

Doble clic en EDITOR.bat (o: python kf4_editor_local.py). Abre el editor en el navegador y:
  - carga las texturas directamente de la ISO (no hace falta exportarlas);
  - "Vista del juego": construye el mapa con el mismo generador que la ISO (texturas, color de vértice,
    piezas completas) y lo enseña tal cual;
  - "Guardar" escribe mapa_torre.json en esta carpeta;
  - "Probar en el juego" guarda, genera la ISO y abre PCSX2 (llama a JUGAR_VALLE.bat editor).

Solo escucha en este PC (127.0.0.1). Ciérralo cerrando su ventana.
"""

import io
import json
import os
import struct
import subprocess
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import kf4_mapdump as md             # noqa: E402
import kf4_editor as ke              # noqa: E402

PUERTO = 8642
ESTADO = {"texturas": {}, "iso": None, "error": None}
CANDADO = threading.Lock()


def buscar_iso():
    """La ISO de King's Field IV: en esta carpeta o en la de encima (FIELDIV-ENGINE: la ISO junto al .exe)."""
    for carpeta in (AQUI, os.path.dirname(AQUI)):
        isos = [f for f in os.listdir(carpeta) if f.lower().endswith(".iso") and "(valle)" not in f
                and "(parche)" not in f]
        isos.sort(key=lambda f: ("(" in f, len(f), f))
        if isos:
            return os.path.join(carpeta, isos[0])
    return None


def cargar_texturas():
    iso = buscar_iso()
    ESTADO["iso"] = iso
    if not iso:
        ESTADO["error"] = "No encuentro la ISO de King's Field IV en esta carpeta"
        return
    try:
        import kf4_tex as kt            # necesita numpy (EDITOR.bat lo instala si falta)
        from kf4_texturas import png
        src = md.Source(iso)
        d099 = src.read("099.map")
        texs, _, _ = kt.load_map_textures(d099)
        por_clave = {(f["TBP"], f["CBP"]): img for f, img in texs.values()}
        for nombre, clave in ke.TEXTURAS.items():
            img = por_clave.get(clave)
            if img is None:
                continue
            ESTADO["texturas"][nombre] = png(img)
        print(f"Texturas cargadas de {os.path.basename(iso)}: {len(ESTADO['texturas'])}")
    except Exception as e:     # la vista sigue funcionando con colores planos
        ESTADO["error"] = f"No pude leer las texturas de la ISO: {e}"
        traceback.print_exc()


def nombre_textura(clave):
    for n, k in ke.TEXTURAS.items():
        if k == clave:
            return n
    return None


def atlas_png(v, tex):
    """Textura de una región del atlas de King's Field (hueco + paleta propia) como PNG, para la vista del juego."""
    import numpy as np
    from kf4_texturas import png
    tbp, cbp = tex
    nombre = f"kf_{tbp:04x}_{cbp:04x}"
    if nombre not in ESTADO["texturas"]:
        h = next((h for h in v.kf_atlas.huecos if h["clave"][0] == tbp), None)
        pal = v.kf_atlas.paletas.get(cbp)
        if h is None or pal is None:
            return None
        img = pal[h["img"]].copy()
        img[..., 3] = 255
        ESTADO["texturas"][nombre] = png(img)
    return nombre


def geometria(mapa):
    """Construye el mapa con el generador y lo devuelve como grupos de triángulos por textura:
    cabecera JSON (longitud u32 + JSON) y luego, por grupo, floats: posición(3) uv(2) color(3)."""
    with CANDADO:
        v = ke.MapaEditor(1, mapa)
        v.construir()
    grupos = {}
    for ch, por_tex in v.geo.render.items():
        for tex, tiras in por_tex.items():
            nombre = nombre_textura(tex) or (atlas_png(v, tex) if getattr(v, "kf_atlas", None) else None) or "?"
            datos = grupos.setdefault(nombre, [])
            for t in tiras:
                for i in range(len(t) - 2):
                    for vtx in (t[i], t[i + 1], t[i + 2]):
                        p, uv, c = vtx[0], vtx[1], vtx[2]
                        datos.extend((p[0], p[2], -p[1], uv[0], uv[1], c[0] / 128.0, c[1] / 128.0, c[2] / 128.0))
    # la colisión, para verla encima: paredes en rojo y suelos en verde
    for kind, col in (("wall", (1.0, 0.25, 0.2)), ("floor", (0.3, 1.0, 0.4))):
        datos = grupos.setdefault("coll:" + kind, [])
        for ch, kinds in v.geo.coll.items():
            for t in kinds[kind]:
                for i in range(len(t) - 2):
                    for p in (t[i], t[i + 1], t[i + 2]):
                        datos.extend((p[0], p[2], -p[1], 0.0, 0.0, *col))
    meta = {"grupos": [{"textura": n, "vertices": len(d) // 8} for n, d in grupos.items()]}
    cab = json.dumps(meta).encode("utf-8")
    cuerpo = b"".join(struct.pack(f"<{len(d)}f", *d) for d in grupos.values())
    return struct.pack("<I", len(cab)) + cab + cuerpo


def comprobar(mapa):
    """Monta el 099.map entero como lo haría "Probar en el juego" (sin tocar la ISO) y dice cuánto ocupa,
    si cabe, y qué avisos hay."""
    import kf4_valle as kv
    iso = ESTADO["iso"]
    if not iso:
        return {"error": "No encuentro la ISO en la carpeta del juego"}
    log, avisos = [], []
    with CANDADO:
        v = ke.MapaEditor(1, mapa)
        v.construir()
        kv.revisar(v.geo, log)
        p = v.inicio
        c = v.celda_en(int((p[0] - v.ox) // v.celda), int((p[1] - v.oy) // v.celda))
        if not isinstance(c, dict) and c != "tapada":        # dentro de una casa también hay suelo
            avisos.append("El inicio del jugador no está sobre un suelo: caerá o no podrá moverse")
        kv.fijar_offset(v)
        src = md.Source(iso)
        nuevo, stats = kv.generar_mapa(src, v, 0.0, log)
    hueco = kv.hueco_mapa(iso)
    if hueco and len(nuevo) > hueco:
        avisos.append(f"No cabe: sobran {len(nuevo) - hueco:,} bytes".replace(",", "."))
    if len(v.spawns_pos) > kv.MAX_SPAWNS:
        avisos.append(f"Hay {len(v.spawns_pos)} enemigos; se colocan {kv.MAX_SPAWNS}")
    for linea in log:
        if "AVISO" in linea or "solap" in linea.lower() and "sin superficies" not in linea:
            avisos.append(linea)
    return {"bytes": len(nuevo), "hueco": hueco, "triangulos": stats.get("tris"), "registros": linea_de(log, "Registros"),
            "avisos": avisos, "log": log[-14:]}


def linea_de(log, prefijo):
    return next((l for l in log if l.startswith(prefijo)), "")


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def responder(self, codigo, tipo, datos):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        ruta = self.path.split("?")[0]
        if ruta in ("/", "/index.html"):
            with open(os.path.join(AQUI, "editor_torre.html"), "rb") as f:
                html = f.read()
            pagina = (b"<!doctype html><html><head><meta charset=utf-8><meta name=viewport "
                      b"content=\"width=device-width,initial-scale=1\"></head><body>" + html + b"</body></html>")
            return self.responder(200, "text/html; charset=utf-8", pagina)
        if ruta == "/api/estado":
            info = {"local": True, "iso": os.path.basename(ESTADO["iso"]) if ESTADO["iso"] else None,
                    "texturas": sorted(ESTADO["texturas"]), "error": ESTADO["error"],
                    "mapa": os.path.isfile(os.path.join(AQUI, "mapa_torre.json"))}
            return self.responder(200, "application/json", json.dumps(info).encode())
        if ruta == "/api/mapa":
            p = os.path.join(AQUI, "mapa_torre.json")
            if not os.path.isfile(p):
                return self.responder(404, "text/plain", b"sin mapa")
            with open(p, "rb") as f:
                return self.responder(200, "application/json", f.read())
        if ruta.startswith("/tex/") and ruta.endswith(".png"):
            n = ruta[5:-4]
            if n in ESTADO["texturas"]:
                return self.responder(200, "image/png", ESTADO["texturas"][n])
        return self.responder(404, "text/plain", b"no encontrado")

    def do_POST(self):
        largo = int(self.headers.get("Content-Length", "0"))
        cuerpo = self.rfile.read(largo)
        try:
            if self.path == "/api/vista":
                return self.responder(200, "application/octet-stream", geometria(json.loads(cuerpo)))
            if self.path == "/api/comprobar":
                return self.responder(200, "application/json", json.dumps(comprobar(json.loads(cuerpo))).encode())
            if self.path == "/api/guardar":
                json.loads(cuerpo)
                with open(os.path.join(AQUI, "mapa_torre.json"), "wb") as f:
                    f.write(cuerpo)
                return self.responder(200, "application/json", b'{"ok":true}')
            if self.path == "/api/jugar":
                json.loads(cuerpo)
                with open(os.path.join(AQUI, "mapa_torre.json"), "wb") as f:
                    f.write(cuerpo)
                bat = os.path.join(AQUI, "JUGAR_VALLE.bat")
                if os.name == "nt":
                    subprocess.Popen(["cmd", "/c", "start", "", bat, "editor"], cwd=AQUI)
                else:
                    subprocess.Popen([sys.executable, os.path.join(AQUI, "kf4_valle.py"), "--zona", "editor"], cwd=AQUI)
                return self.responder(200, "application/json", b'{"ok":true}')
        except Exception as e:
            traceback.print_exc()
            return self.responder(500, "application/json", json.dumps({"error": str(e)}).encode())
        return self.responder(404, "text/plain", b"no encontrado")


def main():
    print("Field4Editor")
    cargar_texturas()
    if ESTADO["error"]:
        print("AVISO:", ESTADO["error"])
    srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    url = f"http://127.0.0.1:{PUERTO}/"
    print(f"Abierto en {url}  (cierra esta ventana para salir)")
    if "--sin-navegador" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
