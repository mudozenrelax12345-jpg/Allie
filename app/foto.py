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
import banco  # noqa: E402
import gemini  # noqa: E402
import reel  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
FOTOS = BASE / "videos" / "fotos"
RECHAZADAS = BASE / "videos" / "rechazadas"
PROPUESTA = BASE / "videos" / "propuesta.json"
DIARIO_ARCHIVO = BASE / "videos" / "diario-fotos.json"

CUANTAS = int(os.environ.get("CUANTAS_FOTOS", "3"))

# Qué se pidió y qué salió en cada intento. Se escribe en disco pase lo que
# pase, porque el log de Actions no es accesible desde fuera del runner.
DIARIO = []


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
    """Devuelve los bytes de una foto aprobada, o None.

    Cada intento deja escrito en DIARIO qué escena se pidió y qué pasó. Sin
    esto, una tanda que falla entera solo deja «ninguna pasó la revisión», y
    los motivos se quedan en el log de Actions, que no se puede leer desde
    fuera. Pasó: tres fotos descartadas y ni idea de si era el generador, el
    revisor o la escena.
    """
    for intento in range(reel.INTENTOS):
        DIARIO.append({"foto": n, "intento": intento + 1, "escena": escena})
        try:
            datos, fallos = reel.kontext(escena, p)
        except reel.SinCuota as e:
            # Esperar no sirve: la cuota es diaria. Se corta la tanda entera.
            DIARIO[-1]["resultado"] = f"sin cuota: {e}"
            raise
        if datos is None:
            motivo = " | ".join(fallos or ["sin motivo"])
            DIARIO[-1]["resultado"] = f"no generó: {motivo}"
            descartes.append(f"foto {n} intento {intento + 1}: no generó · {motivo}")
            log(f"Foto {n}, intento {intento + 1}: {motivo}")
            time.sleep(reel.ESPERAS[min(intento, len(reel.ESPERAS) - 1)])
            continue
        ok, problema = gemini.revisar_imagen(datos)
        if ok:
            DIARIO[-1]["resultado"] = "aprobada"
            log(f"Foto {n} lista y revisada")
            return datos
        DIARIO[-1]["resultado"] = f"descartada por el revisor: {problema}"
        # Guardo la foto rechazada: a veces el que se equivoca es el revisor,
        # y sin la imagen no hay manera de saberlo.
        try:
            RECHAZADAS.mkdir(parents=True, exist_ok=True)
            (RECHAZADAS / f"foto{n}-intento{intento + 1}.jpg").write_bytes(datos)
        except Exception:  # noqa: BLE001
            pass
        descartes.append(f"foto {n} intento {intento + 1}: {problema}")
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
    if os.environ.get("SOLO_SUBIR") == "si":
        # Las fotos ya están bien y lo único que falló fue el alojamiento.
        # Volver a generarlas sería tirar lo que ya pasó la revisión.
        buenas = sorted(FOTOS.glob("*.jpg"))
        log(f"Solo subo: {len(buenas)} fotos ya guardadas")
        return subir_y_guardar(g, buenas, [])
    for viejo in FOTOS.glob("*.jpg"):
        viejo.unlink()
    if RECHAZADAS.exists():
        for viejo in RECHAZADAS.glob("*.jpg"):
            viejo.unlink()

    buenas, descartes = [], []
    try:
        for i, escena in enumerate(g["escenas"], 1):
            datos = una_foto(escena, p, i, descartes)
            if datos is None:
                continue
            destino = FOTOS / f"foto{i}.jpg"
            destino.write_bytes(datos)
            buenas.append(destino)
    except reel.SinCuota as e:
        log(f"Se corta la tanda: {e}")
        descartes.append(f"cortado por falta de cuota: {e}")
    finally:
        guardar_diario(g, descartes)

    # Sin cuota no se genera, pero sí se puede publicar: el banco guarda fotos
    # de Allie ya revisadas de días con cuota. Antes un día sin cuota era un
    # día sin publicar.
    if len(buenas) < CUANTAS:
        faltan = CUANTAS - len(buenas)
        del_banco, _ = banco.coger(faltan, banco.etiqueta_de(g.get("tema", "")))
        if not del_banco:
            del_banco, _ = banco.coger(faltan)
        for f in del_banco:
            destino = FOTOS / f.name
            destino.write_bytes(f.read_bytes())
            buenas.append(destino)
        if del_banco:
            log(f"{len(del_banco)} fotos cogidas del banco")
            descartes.append(f"{len(del_banco)} fotos del banco, no generadas hoy")

    if not buenas:
        raise RuntimeError(
            "Ni se pudo generar ni había nada en el banco. Los motivos de cada "
            f"intento están en videos/{DIARIO_ARCHIVO.name} y las imágenes "
            f"rechazadas en videos/{RECHAZADAS.name}/.")

    return subir_y_guardar(g, buenas, descartes, del_banco_usadas=[
        f for f in buenas if not f.name.startswith("foto")])


def guardar_diario(g, descartes):
    DIARIO_ARCHIVO.write_text(json.dumps({
        "cuando": datetime.now(timezone.utc).isoformat(),
        "tema": g.get("tema", ""), "idea": g.get("idea", ""),
        "escenas_pedidas": g.get("escenas", []),
        "intentos": DIARIO, "descartadas": descartes,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def subir_y_guardar(g, buenas, descartes, del_banco_usadas=()):
    enlaces, fallos_subida = [], []
    for f in buenas:
        try:
            enlaces.append(reel.subir(f, fallos_subida))
        except Exception as e:  # noqa: BLE001
            fallos_subida.append(f"{f.name}: {e}")
            log(f"No se pudo subir {f.name}: {e}")

    # Si no se subió nada, la publicación no sale, así que las fotos del banco
    # vuelven a estar libres. Marcarlas como usadas sin haber salido sería
    # tirar fotos buenas que costaron cuota.
    if del_banco_usadas and not enlaces:
        banco.devolver(del_banco_usadas)

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
