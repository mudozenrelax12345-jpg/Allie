"""Publicar un carrusel en Instagram desde el banco de fotos.

POR QUÉ, con los números delante. El 18 de octubre miramos las cinco últimas
semanas de @allie.the.ai:

    carruseles   6 piezas · alcance mediano 228 · 12 guardados · 6 seguidores
    fotos        4 piezas · alcance mediano 251 ·  4 guardados · 1 seguidor
    reels        6 piezas · alcance mediano 112 ·  0 guardados · 0 seguidores

El carrusel es lo que funciona y era lo único que no se podía publicar solo:
publicar.py sabe subir reels y nada más, así que los carruseles se
programaban a mano en Metricool, que regala veinte al mes. Con cuatro
carruseles a la semana ese tope se agota el día 20.

CÓMO. Instagram los publica en tres pasos en vez de dos: un contenedor por
cada foto (`is_carousel_item`), luego un contenedor CAROUSEL que los agrupa y
lleva el pie, y por último la publicación. Las fotos se sirven desde el
propio repositorio, que es público.

LAS FOTOS SON DE UNA MISMA TANDA, que es lo que hace banco.coger(): misma
ropa, mismo sitio, misma luz. Un carrusel con fotos de tres días distintos se
nota y parece un collage.

EL PIE SE ESCRIBE MIRANDO LAS FOTOS, no el tema. El 15 de octubre un texto
hablaba de brochas y manchas de pintura sobre tres fotos en una cafetería.
"""
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
BASE = Path(__file__).resolve().parent.parent

import banco  # noqa: E402
import main as bot  # noqa: E402
import publicar  # noqa: E402
import reel  # noqa: E402
from ig import Instagram  # noqa: E402

CRUDO = "https://raw.githubusercontent.com/mudozenrelax12345-jpg/Allie/main/banco/fotos/"
CUANTAS = int(float(os.environ.get("FOTOS_CARRUSEL") or 3))
# Con FOTOS_CARRUSEL=1 esto publica una foto suelta, que es lo que lleva el
# jueves en el plan. Instagram no admite un carrusel de una sola imagen.
MINIMO = 1


def log(m):
    print(f"· {m}", flush=True)


def main():
    seco = (os.environ.get("EN_SECO") or "").strip().lower() in ("si", "sí", "true", "1")

    rutas = banco.coger(CUANTAS)
    if not rutas or len(rutas) < MINIMO:
        raise RuntimeError(
            f"El banco no tiene {MINIMO} fotos libres de una misma tanda. "
            f"Devolvió {len(rutas or [])}.")
    nombres = [Path(r).name for r in rutas]
    log(f"{len(nombres)} fotos: {', '.join(nombres)}")

    ya = publicar.publicados()
    publicadas = {a for p in ya for a in (p.get("archivos") or [p.get("archivo")])}
    repetidas = [n for n in nombres if n in publicadas]
    if repetidas:
        raise RuntimeError(f"Estas fotos ya se publicaron: {', '.join(repetidas)}")

    p = reel.persona()
    d = reel.texto_de_las_fotos(p, rutas)
    texto = (d.get("texto") or "").strip()
    if not texto:
        raise RuntimeError("Sin texto no se publica. Un carrusel mudo no dice nada.")
    pie = publicar.con_aviso(texto, " ".join(d.get("hashtags") or []))
    log(f"Pie ({len(pie)} caracteres):\n{pie}")

    urls = [CRUDO + n for n in nombres]
    for u in urls:
        log(f"  {u}")

    if seco:
        log("EN_SECO: no se publica nada.")
        return

    token, ig_id, page_id = bot.credenciales()
    ig = Instagram(token=token, ig_id=ig_id, page_id=page_id)

    # Foto suelta: Instagram no admite un carrusel de una imagen.
    if len(urls) == 1:
        r = ig._req("POST", f"{ig.yo}/media", image_url=urls[0], caption=pie)
        contenedor = r.get("id")
        if not contenedor:
            raise RuntimeError(f"Instagram no devolvió contenedor: {r}")
        log(f"Foto suelta · contenedor {contenedor}")
        return _esperar_y_publicar(ig, contenedor, nombres, pie, ya, "foto")

    # Paso 1 · un contenedor por foto.
    hijos = []
    for u in urls:
        r = ig._req("POST", f"{ig.yo}/media", image_url=u, is_carousel_item="true")
        hijo = r.get("id")
        if not hijo:
            raise RuntimeError(f"Instagram no devolvió contenedor para {u}: {r}")
        hijos.append(hijo)
        log(f"  contenedor {hijo}")

    # Paso 2 · el contenedor del carrusel, que es el que lleva el pie.
    r = ig._req("POST", f"{ig.yo}/media", media_type="CAROUSEL",
                children=",".join(hijos), caption=pie)
    contenedor = r.get("id")
    if not contenedor:
        raise RuntimeError(f"Instagram no devolvió el contenedor del carrusel: {r}")
    log(f"Carrusel {contenedor}")

    return _esperar_y_publicar(ig, contenedor, nombres, pie, ya, "carrusel")


def _esperar_y_publicar(ig, contenedor, nombres, pie, ya, tipo):
    """Instagram procesa el contenedor unos segundos; publicar antes falla."""
    estado = None
    for intento in range(20):
        time.sleep(6)
        e = ig._req("GET", contenedor, fields="status_code,status")
        estado = e.get("status_code")
        log(f"  {(intento + 1) * 6}s · {estado}")
        if estado in ("FINISHED", "ERROR", "EXPIRED"):
            if estado != "FINISHED":
                raise RuntimeError(f"Instagram lo rechazó ({estado}): "
                                   f"{str(e.get('status'))[:300]}")
            break
    if estado != "FINISHED":
        raise RuntimeError("Instagram tardó más de dos minutos en procesarlo.")

    pub = ig._req("POST", f"{ig.yo}/media_publish", creation_id=contenedor)
    media_id = pub.get("id")
    enlace = ""
    try:
        enlace = (ig._req("GET", media_id, fields="permalink") or {}).get("permalink", "")
    except Exception:  # noqa: BLE001
        pass
    log(f"PUBLICADO · {media_id} · {enlace}")

    ya.append({"tipo": tipo, "archivos": nombres, "media_id": media_id,
               "enlace": enlace, "texto": pie,
               "cuando": datetime.now(timezone.utc).isoformat()})
    publicar.REGISTRO.write_text(json.dumps(ya, ensure_ascii=False, indent=1),
                                 encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · carrusel\n\n{detalle}\n",
            encoding="utf-8")
        raise
