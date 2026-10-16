"""Publicar el reel del día en Instagram sin pasar por Metricool.

POR QUÉ. Metricool regala 20 publicaciones por mes natural. El 16 de octubre
iban 17 con quince días por delante: publicar a diario era imposible por eso
y solo por eso, teniendo setenta fotos listas en el banco. La API de
Instagram permite 25 publicaciones cada 24 horas, cinco veces más de lo que
hace falta, y el token ya es el mismo que usa el bot de comentarios.

CÓMO. Instagram publica en dos pasos: primero se crea un «contenedor» con el
vídeo y el texto, Instagram lo procesa unos segundos, y después se publica.
El vídeo se sirve desde el propio repositorio, que es público: una dirección
permanente, sin alojamientos temporales que caducan en horas.

LA ETIQUETA DE IA. Metricool marcaba cada publicación como contenido
generado con IA. La API no tiene ese campo, así que la declaración va escrita
en el texto, visible para quien lo lee. Para la transparencia que exigen el
reglamento europeo y las normas de Meta, una frase que la gente ve es mejor
que una casilla que no ve nadie; pero conviene saber que son cosas distintas
y que esto no enciende el aviso propio de Instagram.

SEGURIDAD. No publica dos veces lo mismo: lleva un registro. No publica sin
texto. Y no publica si el vídeo no está en la rama principal, porque entonces
Instagram no podría descargarlo.
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

import main as bot  # noqa: E402
from ig import IGError, Instagram  # noqa: E402

ULTIMO = BASE / "videos" / "ultimo.json"
REGISTRO = BASE / "videos" / "publicados.json"
CRUDO = "https://raw.githubusercontent.com/mudozenrelax12345-jpg/Allie/main/videos/"

# La declaración, en el texto, porque la API no tiene dónde ponerla.
#
# VA LA PRIMERA, y esto no es una cuestión de estilo. Instagram corta el pie
# a unos 125 caracteres y esconde el resto tras «… más»: una declaración al
# final no la ve casi nadie. El artículo 50.4 del reglamento europeo de IA
# pide revelarlo «de manera clara y distinguible, a más tardar con ocasión
# de la primera exposición». Al final del texto no es la primera exposición;
# es el pie de página de algo que ya te has creído.
AVISO = "🤖 Contenido generado con IA · Allie es un personaje creado con IA"
LIMITE_VISIBLE = 125


def log(m):
    print(f"· {m}", flush=True)


def publicados():
    try:
        return json.loads(REGISTRO.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def con_aviso(texto, hashtags):
    """El texto final: la declaración de IA PRIMERO, luego el post."""
    cuerpo = (texto or "").strip()
    etiquetas = (hashtags or "").strip()
    ya_lo_dice = "generado con IA" in cuerpo[:LIMITE_VISIBLE]
    partes = ([] if ya_lo_dice else [AVISO]) + [cuerpo]
    if etiquetas and etiquetas not in cuerpo:
        partes.append(etiquetas)
    return "\n\n".join(p for p in partes if p)


def main():
    seco = (os.environ.get("EN_SECO") or "").strip().lower() in ("si", "sí", "true", "1")

    d = json.loads(ULTIMO.read_text(encoding="utf-8"))
    archivo = d.get("archivo")
    texto = (d.get("texto") or "").strip()
    if not archivo:
        raise RuntimeError("videos/ultimo.json no dice qué vídeo es.")
    if not texto:
        raise RuntimeError("El reel no tiene texto. No se publica un vídeo mudo.")
    if not (BASE / "videos" / archivo).exists():
        raise RuntimeError(f"No está el fichero {archivo}.")

    ya = publicados()
    if any(p.get("archivo") == archivo for p in ya):
        log(f"{archivo} ya se publicó. No lo repito.")
        return

    url = CRUDO + archivo
    pie = con_aviso(texto, d.get("hashtags"))
    log(f"Vídeo: {url}")
    log(f"Texto ({len(pie)} caracteres):\n{pie}")

    if seco:
        log("EN_SECO: no se publica nada.")
        return

    token, ig_id, page_id = bot.credenciales()
    ig = Instagram(token=token, ig_id=ig_id, page_id=page_id)

    # Paso 1 · el contenedor.
    r = ig._req("POST", f"{ig.yo}/media", media_type="REELS", video_url=url,
                caption=pie, share_to_feed="true")
    contenedor = r.get("id")
    if not contenedor:
        raise RuntimeError(f"Instagram no devolvió contenedor: {r}")
    log(f"Contenedor {contenedor}")

    # Paso 2 · esperar a que lo procese. Publicar antes de tiempo falla.
    estado = None
    for intento in range(30):
        time.sleep(10)
        e = ig._req("GET", contenedor, fields="status_code,status")
        estado = e.get("status_code")
        log(f"  {(intento + 1) * 10}s · {estado}")
        if estado in ("FINISHED", "ERROR", "EXPIRED"):
            if estado != "FINISHED":
                raise RuntimeError(f"Instagram rechazó el vídeo ({estado}): "
                                   f"{str(e.get('status'))[:300]}")
            break
    if estado != "FINISHED":
        raise RuntimeError("Instagram tardó más de cinco minutos en procesar el vídeo.")

    # Paso 3 · publicar.
    pub = ig._req("POST", f"{ig.yo}/media_publish", creation_id=contenedor)
    media_id = pub.get("id")
    enlace = ""
    try:
        enlace = (ig._req("GET", media_id, fields="permalink") or {}).get("permalink", "")
    except Exception:  # noqa: BLE001
        pass
    log(f"PUBLICADO · {media_id} · {enlace}")

    ya.append({"archivo": archivo, "media_id": media_id, "enlace": enlace,
               "cuando": datetime.now(timezone.utc).isoformat(), "texto": pie})
    REGISTRO.write_text(json.dumps(ya, ensure_ascii=False, indent=1), encoding="utf-8")
    d["publicado"] = {"media_id": media_id, "enlace": enlace}
    ULTIMO.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · publicar\n\n{detalle}\n",
            encoding="utf-8")
        raise
