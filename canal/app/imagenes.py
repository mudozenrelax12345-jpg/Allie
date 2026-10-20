"""Genera las imágenes de apoyo en vez de buscarlas en un banco.

Por qué: buscar en Pixabay salía mal de dos maneras a la vez. Casi la mitad
de los clips no tenían nada que ver con lo que se pedía —un canguro cuando
pedí una bolsa de la compra— y otra mitad eran literalmente los mismos
archivos que ya habían salido en el vídeo anterior, porque dos guiones con
palabras parecidas devuelven el mismo primer resultado.

Generarlas resuelve las dos cosas de golpe: salen exactamente de lo que se
está contando, y no existen en ningún otro sitio, así que no pueden
repetirse entre vídeos.

Lee la sección «imagenes:» de material.yml y deja:

  material/generadas/<nombre>.png

Todas comparten el mismo tratamiento —oscuras, de noche o a contraluz, sin
gente reconocible y sin texto— para que peguen con las tarjetas del canal.
"""
import os
import time
from pathlib import Path
from urllib.parse import quote

import requests
import yaml
from PIL import Image

import config

BASE = Path(__file__).resolve().parent.parent
# Se guardan junto a la configuración del vídeo, no en material/, porque
# material/ se borra en cada montaje. Generarlas cuesta media hora: tiene
# sentido hacerlo una vez y guardarlas.
SALIDA = config.VIDEOS / config.cual() / "imagenes"

ANCHO, ALTO = 1920, 1080
INTENTOS = 8

# El sello del canal. Va en todas, para que el vídeo se vea de una pieza.
ESTILO = ("cinematic documentary still, dark moody lighting, deep shadows, "
          "muted desaturated colours with a single warm amber highlight, "
          "shallow depth of field, 35mm photograph, no people's faces, "
          "no text, no letters, no logos, no watermark")


def log(m):
    print(f"· {m}", flush=True)


def url(prompt, semilla):
    clave = os.environ.get("POLLINATIONS_KEY", "").strip()
    texto = f"{prompt}. {ESTILO}"
    base = ("https://gen.pollinations.ai/image/" if clave
            else "https://image.pollinations.ai/prompt/")
    u = (f"{base}{quote(texto)}?width={ANCHO}&height={ALTO}"
         f"&seed={semilla}&nologo=true&model=flux")
    return u + (f"&key={clave}" if clave else "")


def limpiar(ruta):
    """Quita la firma de la esquina.

    El generador estampa su marca abajo a la derecha aunque se le pida que
    no lo haga. Se recorta esa franja y se vuelve a escalar: se pierde un
    3% de imagen y se gana una pantalla limpia."""
    im = Image.open(ruta).convert("RGB")
    a, al = im.size
    im = im.crop((0, 0, int(a * 0.985), int(al * 0.965))).resize((ANCHO, ALTO), Image.LANCZOS)
    im.save(ruta, quality=90)


def una(nombre, prompt, semilla, licencias):
    destino = SALIDA / f"{nombre}.jpg"
    if destino.exists():
        log(f"· {nombre}: ya estaba hecha")
        licencias.append(f"{nombre}: imagen generada para este vídeo · «{prompt}»")
        return True
    for intento in range(INTENTOS):
        try:
            r = requests.get(url(prompt, semilla + intento * 977), timeout=300)
        except requests.RequestException as e:
            log(f"✗ {nombre}: fallo de red ({e})")
            time.sleep(5 + 5 * intento)
            continue
        if r.status_code == 429:
            espera = min(20 + 15 * intento, 75)
            log(f"    nos cortan por ritmo, espero {espera} s")
            time.sleep(espera)
            continue
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
            log(f"✗ {nombre}: devolvió {r.status_code}")
            time.sleep(6)
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(r.content)
        limpiar(destino)
        log(f"✓ {nombre}.png ({len(r.content) // 1024} KB)")
        licencias.append(f"{nombre}: imagen generada para este vídeo, no sale de "
                         f"ningún banco · «{prompt}»")
        return True
    licencias.append(f"{nombre}: NO GENERADA tras {INTENTOS} intentos · «{prompt}»")
    return False


def main():
    cfg = yaml.safe_load(config.ruta("material.yml").read_text(encoding="utf-8"))
    lista = cfg.get("imagenes") or []
    if not lista:
        log("Este vídeo no pide imágenes generadas.")
        return
    # La semilla sale del nombre del vídeo: así dos vídeos distintos nunca
    # pueden producir la misma imagen, ni por casualidad.
    raiz = abs(hash(config.cual())) % 100000
    licencias, hechas = [], 0
    log(f"— {len(lista)} imágenes por generar —")
    for i, im in enumerate(lista):
        if una(im["nombre"], im["busca"], raiz + i * 31, licencias):
            hechas += 1
        time.sleep(2.5)
    log(f"{hechas} de {len(lista)} disponibles")

    parte = BASE / "material" / "LICENCIAS.txt"
    parte.parent.mkdir(parents=True, exist_ok=True)
    with open(parte, "a", encoding="utf-8") as f:
        f.write("\n— Imágenes generadas —\n" + "\n".join(licencias) + "\n")


if __name__ == "__main__":
    main()
