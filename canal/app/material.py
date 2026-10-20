"""Reúne el material visual de un vídeo: documentos y clips de archivo.

Lee material.yml y deja todo en material/:

  material/documentos/DOC-A-carta-supervision-p1.png
  material/clips/B1-escaner.mp4
  material/LICENCIAS.txt      de dónde sale cada cosa y con qué permiso

Los PDF de documentos oficiales son de dominio público (obra del gobierno de
EEUU). Los clips vienen de Pexels, cuya licencia permite uso comercial sin
atribución. LICENCIAS.txt lo deja por escrito, que es lo que hace falta si
algún día hay que apelar una reclamación.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml

import config

# Registro de lo ya gastado. Sin esto, dos guiones con palabras parecidas
# ("capitol", "keyboard", "data center") devuelven el mismo primer resultado
# y medio vídeo sale reciclado del anterior — que es exactamente lo que pasó
# entre el vídeo 1 y el 2: 25 de 54 clips eran el mismo archivo.
REGISTRO = Path(__file__).resolve().parent.parent / "estado" / "usados.json"


def ya_gastados():
    """Los ids que ha usado CUALQUIER otro vídeo."""
    if not REGISTRO.exists():
        return set()
    d = json.loads(REGISTRO.read_text(encoding="utf-8"))
    mio = config.cual()
    return {i for v, ids in d.items() if v != mio for i in ids}


def anotar(ids):
    d = json.loads(REGISTRO.read_text(encoding="utf-8")) if REGISTRO.exists() else {}
    d[config.cual()] = sorted(set(ids))
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")


def identificar(pagina):
    """El número que Pixabay le da al vídeo, que es lo que lo identifica."""
    m = re.search(r"/id-(\d+)", pagina or "")
    return m.group(1) if m else (pagina or "")

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "material"
PEXELS = "https://api.pexels.com/videos/search"
PIXABAY = "https://pixabay.com/api/videos/"


def log(m):
    print(f"· {m}", flush=True)


NAVEGADOR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
             "Accept": "*/*", "Referer": "https://pixabay.com/"}


def descargar(url, destino, cabeceras=None, intentos=5):
    """Pixabay corta por ritmo (429). La única cura es esperar de verdad.

    Con cabeceras de navegador, porque algunos CDN rechazan las peticiones
    peladas, y con esperas largas y crecientes cuando la respuesta es 429.
    """
    ultimo = None
    for i in range(intentos):
        try:
            r = requests.get(url, headers=cabeceras or NAVEGADOR, timeout=120, stream=True)
            if r.status_code == 429:
                espera = int(r.headers.get("Retry-After") or 0) or (15 * (i + 1))
                log(f"    nos cortan por ritmo, espero {espera}s")
                time.sleep(espera)
                ultimo = requests.HTTPError("429 Too Many Requests")
                continue
            r.raise_for_status()
            break
        except requests.HTTPError as e:
            ultimo = e
            time.sleep(4 + 6 * i)
        except Exception as e:  # noqa: BLE001
            ultimo = e
            time.sleep(3 + 4 * i)
    else:
        raise ultimo
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "wb") as f:
        for trozo in r.iter_content(1 << 16):
            f.write(trozo)
    return destino.stat().st_size


# ---------------------------------------------------------------- documentos
def documentos(lista, licencias):
    carpeta = SALIDA / "documentos"
    for doc in lista:
        nombre, url = doc["nombre"], doc["url"]
        paginas = int(doc.get("paginas", 1))
        pdf = carpeta / f"{nombre}.pdf"
        try:
            tam = descargar(url, pdf, {"User-Agent": "Mozilla/5.0 (canal; investigacion)"})
        except Exception as e:  # noqa: BLE001
            log(f"✗ {nombre}: {e}")
            licencias.append(f"{nombre}: NO DESCARGADO ({e}) · {url}")
            continue
        log(f"✓ {nombre}.pdf ({tam // 1024} KB)")
        try:
            subprocess.run(["pdftoppm", "-png", "-r", "150", "-f", "1", "-l", str(paginas),
                            str(pdf), str(carpeta / nombre)], check=True)
            hechas = sorted(carpeta.glob(f"{nombre}-*.png"))
            log(f"  → {len(hechas)} página(s) en PNG")
        except Exception as e:  # noqa: BLE001
            log(f"  ⚠ no pude convertirlo a imagen: {e}")
        licencias.append(f"{nombre}: documento oficial del gobierno de EEUU, "
                         f"dominio público · {url}")


# --------------------------------------------------------------------- clips
def _mejor(opciones, ancho_max=1920):
    """El archivo de más calidad que no pase de Full HD."""
    validos = [f for f in opciones if f.get("width")]
    if not validos:
        return None
    caben = [f for f in validos if f["width"] <= ancho_max] or validos
    return max(caben, key=lambda f: f["width"])


def buscar_pexels(busca, clave):
    """Devuelve varios candidatos, para poder descartar los ya usados."""
    r = requests.get(PEXELS, headers={"Authorization": clave}, timeout=60,
                     params={"query": busca, "per_page": 10,
                             "orientation": "landscape", "size": "medium"})
    r.raise_for_status()
    salida = []
    for v in r.json().get("videos", []):
        f = _mejor(v.get("video_files", []))
        if f:
            salida.append((f["link"], f["width"], f["height"],
                           v.get("user", {}).get("name", "?"), v.get("url", ""), "Pexels"))
    return salida


def buscar_pixabay(busca, clave):
    r = requests.get(PIXABAY, timeout=60,
                     params={"key": clave, "q": busca, "video_type": "film",
                             "safesearch": "true", "per_page": 10})
    r.raise_for_status()
    salida = []
    for v in r.json().get("hits", []):
        f = _mejor(list(v.get("videos", {}).values()))
        if f:
            salida.append((f["url"], f["width"], f["height"],
                           v.get("user", "?"), v.get("pageURL", ""), "Pixabay"))
    return salida


def clips(lista, licencias):
    """Usa Pexels si hay clave; si no, Pixabay. Si no hay ninguna, lo dice y sigue."""
    pexels = os.environ.get("PEXELS_API_KEY", "").strip()
    pixabay = os.environ.get("PIXABAY_API_KEY", "").strip()
    if pexels:
        fuente, buscar, clave = "Pexels", buscar_pexels, pexels
    elif pixabay:
        fuente, buscar, clave = "Pixabay", buscar_pixabay, pixabay
    else:
        log("Sin clave de Pexels ni de Pixabay: me salto los clips.")
        log("Los documentos sí se han hecho.")
        licencias.append("CLIPS: no descargados, faltaba la clave del banco de vídeo.")
        return
    log(f"Banco de vídeo: {fuente}")

    carpeta = SALIDA / "clips"
    # Lo ya usado en otros vídeos cuenta como visto: así no se repite nada.
    ajenos = ya_gastados()
    if ajenos:
        log(f"{len(ajenos)} clips ya usados en otros vídeos: quedan descartados")
    vistos = set()          # para que dos búsquedas parecidas no traigan el mismo vídeo
    usados_aqui = []
    for c in lista:
        nombre, busca = c["nombre"], c["busca"]
        try:
            candidatos = buscar(busca, clave)
        except Exception as e:  # noqa: BLE001
            log(f"✗ {nombre}: fallo al buscar «{busca}»: {e}")
            licencias.append(f"{nombre}: ERROR al buscar «{busca}» ({e})")
            continue
        hallazgo = next((h for h in candidatos
                         if h[0] not in vistos and identificar(h[4]) not in ajenos), None)
        if not hallazgo:
            log(f"✗ {nombre}: sin resultados nuevos para «{busca}»")
            licencias.append(f"{nombre}: SIN RESULTADOS para «{busca}»")
            continue
        vistos.add(hallazgo[0])
        enlace, w, h, autor, pagina, banco = hallazgo
        usados_aqui.append(identificar(pagina))
        try:
            tam = descargar(enlace, carpeta / f"{nombre}.mp4")
        except Exception as e:  # noqa: BLE001
            log(f"✗ {nombre}: no se pudo descargar: {e}")
            licencias.append(f"{nombre}: NO DESCARGADO ({type(e).__name__}: {e}) · {enlace}")
            continue
        time.sleep(1.2)          # no atropellar al banco de vídeo
        log(f"✓ {nombre}.mp4 ({tam // (1024*1024)} MB · {w}x{h})")
        licencias.append(f"{nombre}: {banco}, licencia libre para uso comercial · "
                         f"autor: {autor} · {pagina}")
    anotar(usados_aqui)


# ---------------------------------------------------------------------- main
def main():
    cfg = yaml.safe_load(config.ruta("material.yml").read_text(encoding="utf-8"))
    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    licencias = []

    log("— Documentos —")
    documentos(cfg.get("documentos", []), licencias)
    log("— Clips —")
    clips(cfg.get("clips", []), licencias)

    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "LICENCIAS.txt").write_text(
        "De dónde sale cada material y con qué permiso.\n"
        "Guarda este archivo: es lo que vale como defensa si alguna vez\n"
        "hay que responder a una reclamación de derechos.\n\n"
        "Si los clips vienen de Pixabay, sus condiciones de API piden que\n"
        "menciones a Pixabay en la descripción del vídeo. Una línea basta.\n\n"
        + "\n".join(licencias) + "\n", encoding="utf-8")
    log("Listo. Todo en material/")


if __name__ == "__main__":
    main()
