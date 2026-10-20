"""Comprobaciones de la subida a YouTube, sin tocar la red ni el canal.

POR QUÉ ESTA PRUEBA. Subir un vídeo es la única cosa de toda la fábrica que
no se puede ensayar: o sube de verdad o no sube, y lo que sube queda en un
canal público. Así que todo lo que se puede comprobar antes, se comprueba
antes.

Lo que se mira, y de dónde sale cada cosa:

  · Que `selfDeclaredMadeForKids` va SIEMPRE. Si no se declara, YouTube no
    rechaza la subida con un mensaje claro: la acepta y deja el vídeo en
    limbo. Es el fallo más fácil de no ver.
  · Que un título largo se corta. El tope son 100 caracteres y la respuesta
    de YouTube a un título de 101 es un 400 sin explicación, DESPUÉS de haber
    subido el fichero entero.
  · Que las etiquetas se cortan por la suma, no por una. Son 500 caracteres
    entre todas, y las que llevan espacios cuentan dos más.
  · Que sin título no se sube nada. Un vídeo sin título en un canal es peor
    que un vídeo que no está.
  · Que NINGUNA clave aparece por pantalla. Lo que se imprime en Actions
    acaba en un fichero del repositorio.
  · Que una miniatura que falla no tira una subida que salió bien.

Esta prueba usa ficheros temporales: una prueba que mira el estado de
producción no es una prueba.
"""
import json
import os
import sys
import tempfile
from io import StringIO
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

CLAVES = {"YT_CLIENT_ID": "id-secretisimo-123",
          "YT_CLIENT_SECRET": "secreto-secretisimo-456",
          "YT_REFRESH_TOKEN": "refresco-secretisimo-789"}
os.environ.update(CLAVES)

import subir  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que + (f" · {detalle}" if detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


class Respuesta:
    def __init__(self, codigo=200, cuerpo=None, cabeceras=None):
        self.status_code = codigo
        self._cuerpo = cuerpo if cuerpo is not None else {}
        self.headers = cabeceras or {}
        self.text = json.dumps(self._cuerpo)

    def json(self):
        return self._cuerpo


def main():
    # ── 1 · El cuerpo que se le manda a YouTube ────────────────────────────
    d = {"titulo": "Un título normal", "descripcion": "Dos frases.",
         "etiquetas": ["hertz", "ai"]}
    c = subir.cuerpo(d, "unlisted")
    comprobar("se declara si es contenido para niños",
              "selfDeclaredMadeForKids" in c["status"],
              "sin esto YouTube deja el vídeo en limbo")
    comprobar("por omisión NO es para niños", c["status"]["selfDeclaredMadeForKids"] is False)
    comprobar("la privacidad pedida es la que va", c["status"]["privacyStatus"] == "unlisted")
    comprobar("lleva categoría", bool(c["snippet"]["categoryId"]))
    comprobar("lleva idioma del audio", c["snippet"]["defaultAudioLanguage"] == "en",
              "sin esto YouTube adivina y a veces se equivoca")

    # ── 2 · Los topes de YouTube ───────────────────────────────────────────
    largo = subir.cuerpo({"titulo": "A" * 150}, "private")
    comprobar("un título de 150 se corta a 100",
              len(largo["snippet"]["title"]) <= subir.TOPE_TITULO,
              f"quedó en {len(largo['snippet']['title'])}")

    descomunal = subir.cuerpo({"titulo": "x", "descripcion": "B" * 6000}, "private")
    comprobar("una descripción de 6000 se corta a 5000",
              len(descomunal["snippet"]["description"]) <= subir.TOPE_DESCRIPCION)

    muchas = subir.cuerpo({"titulo": "x", "etiquetas": [f"etiqueta numero {i}"
                                                        for i in range(80)]}, "private")
    coste = sum(len(e) + 1 + (2 if " " in e else 0) for e in muchas["snippet"]["tags"])
    comprobar("las etiquetas se cortan por la SUMA, no por una",
              coste <= subir.TOPE_ETIQUETAS, f"suman {coste}")

    picudo = subir.cuerpo({"titulo": "Por qué <esto> falla"}, "private")
    comprobar("los signos < y > no llegan a YouTube",
              "<" not in picudo["snippet"]["title"] and ">" not in picudo["snippet"]["title"],
              "devuelven un 400 sin explicar nada")

    # ── 3 · Sin título no se sube ──────────────────────────────────────────
    try:
        subir.cuerpo({"descripcion": "algo"}, "private")
        comprobar("sin título no se sube", False, "lo dejó pasar")
    except RuntimeError:
        comprobar("sin título no se sube", True)

    # ── 4 · Una privacidad rara se para antes de subir ─────────────────────
    os.environ["PRIVACIDAD"] = "publico"
    os.environ["MP4"] = __file__      # existe, para llegar a la comprobación
    try:
        subir.main()
        comprobar("una privacidad mal escrita se para", False, "siguió adelante")
    except RuntimeError as e:
        comprobar("una privacidad mal escrita se para", "privacidad" in str(e).lower())
    os.environ.pop("PRIVACIDAD", None)

    # ── 5 · Ninguna clave aparece por pantalla ─────────────────────────────
    # Google contesta 400 al pedir el token: el peor momento, el de más
    # tentación de imprimir el cuerpo entero para ver qué pasa.
    def post_que_falla(url, **kw):
        return Respuesta(400, {"error": "invalid_grant",
                               "client_id": CLAVES["YT_CLIENT_ID"]})

    antes = subir.requests.post
    subir.requests.post = post_que_falla
    salida = StringIO()
    stdout = sys.stdout
    sys.stdout = salida
    try:
        subir.acceso()
        error = ""
    except RuntimeError as e:
        error = str(e)
    finally:
        sys.stdout = stdout
        subir.requests.post = antes
    escrito = salida.getvalue() + error
    for nombre, valor in CLAVES.items():
        comprobar(f"{nombre} no se imprime ni fallando", valor not in escrito)
    comprobar("pero sí se dice qué pasó", "invalid_grant" in error,
              "un error mudo no sirve de nada")

    # ── 6 · Una miniatura que falla no tira la subida ──────────────────────
    def post_mini_falla(url, **kw):
        return Respuesta(403, {"error": "quotaExceeded"})

    subir.requests.post = post_mini_falla
    tmp = Path(tempfile.mkdtemp())
    mini = tmp / "m.png"
    mini.write_bytes(b"\x89PNG" + b"0" * 100)
    salida = StringIO()
    sys.stdout = salida
    try:
        resultado = subir.poner_miniatura("token", "abc123", mini)
        reventó = False
    except Exception:  # noqa: BLE001
        reventó = True
        resultado = None
    finally:
        sys.stdout = stdout
        subir.requests.post = antes
    comprobar("una miniatura que falla no tira la subida",
              not reventó and resultado is False)
    comprobar("y no se inventa que la puso", resultado is False)

    # ── 7 · Una miniatura de 3 MB no se intenta siquiera ───────────────────
    gorda = tmp / "gorda.png"
    gorda.write_bytes(b"0" * (3 * 1024 * 1024))
    salida = StringIO()
    sys.stdout = salida
    try:
        r = subir.poner_miniatura("token", "abc123", gorda)
    finally:
        sys.stdout = stdout
    comprobar("una miniatura por encima de 2 MB ni se intenta", r is False,
              "el tope de YouTube son 2 MB")

    # ── 8 · Falta una clave: se dice cuál, sin enseñar las otras ───────────
    guardado = os.environ.pop("YT_REFRESH_TOKEN")
    try:
        subir.credenciales()
        comprobar("si falta un secreto se para", False, "siguió sin él")
    except subir.SinCredenciales as e:
        comprobar("si falta un secreto se para y se dice cuál",
                  "YT_REFRESH_TOKEN" in str(e))
        comprobar("y no se enseñan los que sí están",
                  CLAVES["YT_CLIENT_ID"] not in str(e))
    os.environ["YT_REFRESH_TOKEN"] = guardado

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nla subida está como tiene que estar", flush=True)


if __name__ == "__main__":
    main()
