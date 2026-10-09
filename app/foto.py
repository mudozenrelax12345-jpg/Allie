"""Genera fotos sueltas de Allie, revisadas, y las deja listas para publicar.

Hasta ahora solo existía la vía del reel: cuatro fotos y un vídeo. Un reel que
falla no deja nada, y una cuenta de Instagram vive de fotos sueltas.

Lo que de verdad cambia respecto a lo que se publicó antes es el generador. Las
fotos antiguas salían de un modelo que no copia la cara de la referencia, así
que Allie no era la misma mujer de una semana a otra. Esto usa FLUX.1 Kontext,
que es un modelo de edición: se le da la foto de Allie y una escena y devuelve
a la misma persona en otro sitio.

Cada foto pasa por el revisor antes de guardarse. Y si una escena falla dos
veces, se le quita lo que la está rompiendo en vez de insistir con lo mismo.

Deja:
  videos/fotos/foto1.jpg …     para poder mirarlas
  videos/propuesta.json        escenas, texto del post y direcciones públicas
"""
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402
import reel  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
FOTOS = BASE / "videos" / "fotos"
PROPUESTA = BASE / "videos" / "propuesta.json"

CUANTAS = int(os.environ.get("CUANTAS_FOTOS", "3"))


def log(m):
    print(f"· {m}", flush=True)


def idea(p, cuantas):
    """Un tema y las escenas, con las reglas que ya sabemos que hacen falta."""
    temas = p.get("temas_reel") or ["un día en Madrid"]
    tema = os.environ.get("TEMA", "").strip() or random.choice(temas)
    prompt = f"""Eres el community manager de {p.get('nombre', 'Allie')} en Instagram.
Su forma de ser: {p.get('personalidad', '')}
Datos suyos: {p.get('sobre_ella', '')}

Prepara una PUBLICACIÓN de {cuantas} fotos sobre: "{tema}".
Las fotos van juntas en el mismo post, así que tienen que ser el mismo momento:
la misma ropa, el mismo sitio, la misma luz. Lo que cambia es el plano y la pose.

Devuelve SOLO un JSON:
{{
 "idea": "la idea en una frase, en español",
 "escenas": [{", ".join(['"escena en inglés"'] * cuantas)}],
 "texto": "texto del post en español: primera línea con gancho, 3-5 líneas, acaba con una pregunta",
 "hashtags": ["#...", "..."]
}}

Reglas de las escenas, y son estrictas porque cada una viene de un fallo real:
- En inglés y muy descriptivas, pero SOLO del sitio, la ropa, la pose, la luz
  y el encuadre. NUNCA describas cómo es ella: ni el color del pelo, ni los
  ojos, ni la edad, ni «a young woman with…». Esto es lo más importante de
  todo. El generador parte de una foto suya, y si el texto dice «pelo
  castaño» le hace caso al texto y dibuja a otra mujer. Pasó: de dos fotos,
  la que decía «long brown hair» salió morena y no era Allie; la que empezaba
  por «the same young woman in the same sweater» salió ella.
- Empieza cada escena por «The same woman, » y sigue con el sitio y la ropa.
- SOLO planos de medio cuerpo o primeros planos («upper-body shot», «medium
  shot from the waist up», «close-up»). Nada de cuerpo entero: ahí es donde se
  inventan piernas.
- NUNCA sujeta nada con las manos. Ni taza, ni móvil, ni libro, ni correa, ni
  pincel. Una mano agarrando un objeto fino es lo que peor hace el generador y
  tira la publicación entera.
- La boca, siempre cerrada o con una sonrisa suave de labios juntos. Nunca
  riendo a carcajadas, hablando, cantando ni comiendo.
- Nada de texto, logotipos ni marcas dentro de la imagen.
- Contenido apto para todos los públicos.
Reglas del texto: 4 o 5 hashtags, incluye {p.get('hashtags_base', ['#Allie'])}."""
    g = gemini.json_(prompt)
    escenas = (g.get("escenas") or [])[:cuantas]
    while len(escenas) < cuantas:
        escenas.append(escenas[-1] if escenas else tema)
    g["escenas"], g["tema"] = escenas, tema
    return g


def una_foto(escena, p, n, descartes):
    """Devuelve los bytes de una foto aprobada, o None."""
    for intento in range(reel.INTENTOS):
        datos, fallos = reel.kontext(escena, p)
        if datos is None:
            log(f"Foto {n}, intento {intento + 1}: " + " | ".join(fallos or ["sin motivo"]))
            time.sleep(reel.ESPERAS[min(intento, len(reel.ESPERAS) - 1)])
            continue
        ok, problema = gemini.revisar_imagen(datos)
        if ok:
            log(f"Foto {n} lista y revisada")
            return datos
        descartes.append(f"foto {n}: {problema}")
        log(f"Foto {n} descartada ({problema})")
        if intento == 1:
            escena = reel.sin_manos(escena)
            log(f"Foto {n}: quito las manos de la escena")
        time.sleep(2)
    log(f"Foto {n}: no sale")
    return None


def main():
    p = reel.persona()
    log("Pensando la publicación…")
    g = idea(p, CUANTAS)
    log(f"Tema: {g.get('tema')} · {g.get('idea')}")

    FOTOS.mkdir(parents=True, exist_ok=True)
    for viejo in FOTOS.glob("*.jpg"):
        viejo.unlink()

    buenas, descartes = [], []
    for i, escena in enumerate(g["escenas"], 1):
        datos = una_foto(escena, p, i, descartes)
        if datos is None:
            continue
        destino = FOTOS / f"foto{i}.jpg"
        destino.write_bytes(datos)
        buenas.append(destino)

    if not buenas:
        raise RuntimeError("Ninguna de las fotos pasó la revisión. No publico nada.")

    enlaces, fallos_subida = [], []
    for f in buenas:
        try:
            enlaces.append(reel.subir(f))
        except Exception as e:  # noqa: BLE001
            fallos_subida.append(f"{f.name}: {e}")
            log(f"No se pudo subir {f.name}: {e}")

    hashtags = " ".join(h if str(h).startswith("#") else f"#{h}"
                        for h in g.get("hashtags", []))
    PROPUESTA.write_text(json.dumps({
        "tema": g.get("tema", ""), "idea": g.get("idea", ""),
        "texto": g.get("texto", ""), "hashtags": hashtags,
        "escenas": g["escenas"], "fotos": [f.name for f in buenas],
        "enlaces": enlaces, "fallos_subida": fallos_subida,
        "descartadas": descartes, "creado": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"{len(buenas)} de {CUANTAS} fotos listas · {len(enlaces)} subidas")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · fotos\n\n{detalle}\n",
            encoding="utf-8")
        sys.exit(1)
