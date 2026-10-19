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
import sitios  # noqa: E402
from ig import Instagram  # noqa: E402

RAIZ = "https://raw.githubusercontent.com/mudozenrelax12345-jpg/Allie/main/"
CRUDO = RAIZ + "banco/fotos/"
CUANTAS = int(float(os.environ.get("FOTOS_CARRUSEL") or 3))
COLA = BASE / "contenido" / "cola.json"
# Con FOTOS_CARRUSEL=1 esto publica una foto suelta, que es lo que lleva el
# jueves en el plan. Instagram no admite un carrusel de una sola imagen.
MINIMO = 1


def log(m):
    print(f"· {m}", flush=True)


def siguiente_de_la_cola():
    """La primera pieza preparada a mano sin publicar, o None.

    Las piezas de la cola son las que se guardan: listas de sitios reales
    con horarios comprobados. El texto automático describe la foto, que
    está bien para el día a día pero nadie guarda «qué luz tan bonita».
    """
    try:
        d = json.loads(COLA.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None, None
    for pieza in d.get("piezas", []):
        if not pieza.get("usado"):
            return pieza, d
    return None, d


def marcar_usada(pieza, cola):
    pieza["usado"] = datetime.now(timezone.utc).isoformat()
    COLA.write_text(json.dumps(cola, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    seco = (os.environ.get("EN_SECO") or "").strip().lower() in ("si", "sí", "true", "1")

    # coger() devuelve (rutas, índice) y MARCA las fotos como usadas. Si
    # después falla cualquier cosa hay que devolverlas, o cada intento
    # fallido se come fotos buenas que nunca llegaron a publicarse. El 18 de
    # octubre un simple ensayo en seco se comió tres.
    pieza, cola = siguiente_de_la_cola()
    if pieza:
        log(f"De la cola: «{pieza['titulo']}»")
    # Con etiqueta, para que las fotos no contradigan al texto: una lista de
    # cafeterías con fotos en la calle chirría aunque nadie sepa decir por qué.
    # Una pieza puede traer SUS PROPIAS imágenes en vez de fotos de Allie:
    # el pack de Halloween se anuncia enseñando las láminas, no su cara.
    propias = (pieza or {}).get("imagenes")
    if propias:
        rutas = [BASE / r for r in propias]
        faltan = [str(r) for r in rutas if not r.exists()]
        if faltan:
            raise RuntimeError("No están estas imágenes: " + ", ".join(faltan))
        log(f"{len(rutas)} imágenes propias de la pieza")
        try:
            return _publicar(rutas, seco, pieza, propias)
        finally:
            if pieza and not seco:
                marcar_usada(pieza, cola)

    rutas, _ = banco.coger(CUANTAS, (pieza or {}).get("etiqueta"))
    try:
        salida = _publicar(rutas, seco, pieza)
        if pieza and not seco:
            marcar_usada(pieza, cola)
        return salida
    except Exception:
        banco.devolver(rutas)
        log(f"Devuelvo al banco las {len(rutas)} fotos: no se publicó nada")
        raise


def _publicar(rutas, seco, pieza=None, propias=None):
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

    if pieza:
        texto, etiquetas = pieza.get("texto", "").strip(), pieza.get("hashtags", "")
    else:
        p = reel.persona()
        d = reel.texto_de_las_fotos(p, rutas)
        texto = (d.get("texto") or "").strip()
        etiquetas = " ".join(d.get("hashtags") or [])
    if not texto:
        raise RuntimeError("Sin texto no se publica. Un carrusel mudo no dice nada.")
    pie = publicar.con_aviso(texto, etiquetas)
    log(f"Pie ({len(pie)} caracteres):\n{pie}")

    urls = [RAIZ + r for r in propias] if propias else [CRUDO + n for n in nombres]
    for u in urls:
        log(f"  {u}")

    if seco:
        log("EN_SECO: no se publica nada.")
        banco.devolver(rutas)
        log("Y devuelvo las fotos al banco: un ensayo no gasta material.")
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

    # Paso 2 · el contenedor del carrusel, que es el que lleva el pie y,
    # si lo hay, la ubicación. La ubicación mete la publicación en el feed
    # de ese sitio, que es donde mira quien busca dónde ir en Madrid. Si no
    # la hay, se publica igual: nunca al revés.
    extra = {}
    lugar = (pieza or {}).get("ubicacion")
    if lugar:
        ident, detalle = sitios.buscar(ig, lugar)
        if ident:
            extra["location_id"] = ident
            log(f"Ubicación: {lugar} → {detalle}")
        else:
            log(f"Sin ubicación ({lugar}): {detalle}")
    r = ig._req("POST", f"{ig.yo}/media", media_type="CAROUSEL",
                children=",".join(hijos), caption=pie, **extra)
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
