"""Comprueba que a Cloudflare se le pueden mandar VARIAS imágenes.

POR QUÉ EXISTE ESTO. El 16 de octubre descubrí, preparando la venta a
marcas, que el generador sólo mandaba una imagen: la de Allie. Es decir que
la frase «mándame una foto de tu producto y te hago la imagen» no se podía
cumplir — se podía generar «un tarro blanco cualquiera», no EL tarro del
cliente. Un muestrario precioso y una promesa imposible.

El modelo admite input_image_0 … input_image_3. Esta prueba fija que las
mandamos de verdad, que no nos pasamos de cuatro y que todas van por debajo
de 512×512, que es el límite que impone el modelo y el error más silencioso
de todos: si una se pasa, la petición falla entera sin decir por qué.

No toca la red: suplanta requests.post y mira qué se le iba a enviar.
"""
import os
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("CF_ACCOUNT_ID", "cuenta-de-mentira")
os.environ.setdefault("CF_API_TOKEN", "ficha-de-mentira")

import cloudflare  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(f"{'ok  ' if bien else 'MAL '} {que}" + (f" · {detalle}" if detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


def foto(lado=900, color=(120, 90, 60)):
    b = BytesIO()
    Image.new("RGB", (lado, lado), color).save(b, "JPEG")
    return b.getvalue()


class Respuesta:
    status_code = 500
    text = "no hace falta que conteste: sólo miramos lo que se envía"

    def json(self):
        return {"success": False, "errors": ["prueba"]}


enviados = []


def falso_post(url, **kw):
    enviados.append(kw)
    return Respuesta()


cloudflare.requests.post = falso_post

# El freno del cupo lee un fichero de gasto REAL. Una prueba que mira el
# estado de producción no es una prueba: el 18 de octubre esta empezó a
# fallar sola porque ese día se había gastado cupo de verdad. Fichero
# aparte y techo alto: aquí se mide otra cosa.
import tempfile  # noqa: E402
cloudflare.GASTO = Path(tempfile.mkdtemp()) / "gasto.jsonl"
cloudflare.TECHO_NEURONAS = 10 ** 9


def main():
    allie = foto(1200, (200, 180, 160))
    producto = foto(800, (30, 60, 120))
    otro = foto(640, (90, 150, 90))

    # 1 · Con extras, van todas.
    enviados.clear()
    cloudflare.generar(allie, "una escena", modelos=["modelo-de-prueba"],
                       extras=[producto, otro])
    comprobar("se envió algo", bool(enviados))
    if not enviados:
        return
    ficheros = enviados[0].get("files") or {}
    comprobar("va la foto de Allie", "input_image_0" in ficheros)
    comprobar("va el producto del cliente", "input_image_1" in ficheros,
              " ".join(sorted(ficheros)))
    comprobar("va la segunda imagen extra", "input_image_2" in ficheros)

    # 2 · Ninguna se pasa de 512, que es el límite del modelo.
    grandes = []
    for nombre, (_, datos, _) in ficheros.items():
        im = Image.open(BytesIO(datos))
        if max(im.size) > 512:
            grandes.append(f"{nombre}: {im.size[0]}×{im.size[1]}")
    comprobar("ninguna imagen se pasa de 512 px", not grandes, " | ".join(grandes))

    # 3 · No se mandan más de cuatro: la quinta se descarta en vez de romper
    #     la petición entera.
    enviados.clear()
    cloudflare.generar(allie, "una escena", modelos=["modelo-de-prueba"],
                       extras=[producto] * 6)
    ficheros = enviados[0].get("files") or {}
    comprobar("nunca se mandan más de cuatro imágenes", len(ficheros) <= 4,
              f"iban {len(ficheros)}")
    comprobar("y las que van se llaman input_image_0..3",
              set(ficheros) <= {f"input_image_{i}" for i in range(4)},
              " ".join(sorted(ficheros)))

    # 4 · Sin extras sigue funcionando igual que siempre.
    enviados.clear()
    cloudflare.generar(allie, "una escena", modelos=["modelo-de-prueba"])
    ficheros = enviados[0].get("files") or {}
    comprobar("sin extras va sólo la foto de Allie",
              list(ficheros) == ["input_image_0"], " ".join(sorted(ficheros)))

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nTodo bien.", flush=True)


if __name__ == "__main__":
    main()
