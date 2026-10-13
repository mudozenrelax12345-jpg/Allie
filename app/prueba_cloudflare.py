"""Comprueba el camino de Cloudflare sin gastar ni una neurona.

No llama a Cloudflare: sustituye requests.post por uno de mentira y mira qué
se le habría mandado. Lo que se comprueba es justo lo que la documentación
dice que rompe la llamada, porque equivocarse en cualquiera de estas cuatro
cosas da un error que no explica nada:

  · la entrada va como multipart/form-data, no como JSON
  · la referencia tiene que medir menos de 512×512
  · la cabecera Content-Type NO se pone a mano (se perdería el «boundary»)
  · la imagen vuelve en base64 dentro de result.image

Y además, que sin credenciales esto se salta en silencio en vez de tumbar el
reel, y que si el modelo pequeño falla se prueba el grande.
"""
import base64
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloudflare  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que
          + (f"  ·  {detalle}" if not bien and detalle else ""), flush=True)
    if not bien:
        fallos.append(que)


def jpeg(ancho, alto, color=(120, 90, 60)):
    b = io.BytesIO()
    Image.new("RGB", (ancho, alto), color).save(b, "JPEG", quality=92)
    return b.getvalue()


class Respuesta:
    def __init__(self, codigo=200, cuerpo=None, texto=""):
        self.status_code, self._cuerpo, self.text = codigo, cuerpo, texto

    def json(self):
        if self._cuerpo is None:
            raise ValueError("no es JSON")
        return self._cuerpo


def con_post(devuelve, prueba):
    """`devuelve` recibe (modelo, kwargs) y da una Respuesta o una excepción."""
    orig, llamadas = cloudflare.requests.post, []

    def falso(url, **kw):
        modelo = url.split("/ai/run/", 1)[1]
        llamadas.append({"url": url, "modelo": modelo, **kw})
        r = devuelve(modelo, kw)
        if isinstance(r, Exception):
            raise r
        return r

    cloudflare.requests.post = falso
    try:
        return prueba(), llamadas
    finally:
        cloudflare.requests.post = orig


def bien_hecha(modelo, kw):
    return Respuesta(200, {"success": True,
                           "result": {"image": base64.b64encode(jpeg(1024, 1280)).decode()}})


def main(monkeypatch_env=None):
    import os
    os.environ["CF_ACCOUNT_ID"] = ""
    os.environ["CF_API_TOKEN"] = ""

    # 1 · Sin credenciales no se intenta nada y el reel sigue por Hugging Face.
    comprobar("sin credenciales, hay() dice que no", cloudflare.hay() is False)
    try:
        cloudflare.generar(jpeg(800, 1000), "lo que sea")
        comprobar("sin credenciales avisa en vez de llamar", False, "no avisó")
    except cloudflare.SinCredenciales:
        comprobar("sin credenciales avisa en vez de llamar", True)
    except Exception as e:  # noqa: BLE001
        comprobar("sin credenciales avisa en vez de llamar", False,
                  f"{type(e).__name__}: {e}")

    os.environ["CF_ACCOUNT_ID"] = "cuenta-de-mentira"
    os.environ["CF_API_TOKEN"] = "ficha-de-mentira"
    comprobar("con credenciales, hay() dice que sí", cloudflare.hay() is True)

    # 2 · Una generación normal.
    (datos, segundos, modelo), llamadas = con_post(
        bien_hecha, lambda: cloudflare.generar(jpeg(1200, 1500), "Allie en una cafetería"))

    comprobar("devuelve una imagen", bool(datos) and len(datos) > 2000,
              f"{len(datos or b'')} bytes")
    try:
        im = Image.open(io.BytesIO(datos))
        comprobar("y se puede abrir", im.size[0] > 0, str(im.size))
    except Exception as e:  # noqa: BLE001
        comprobar("y se puede abrir", False, str(e))
    comprobar("empieza por el modelo barato",
              modelo.endswith("klein-4b"), modelo)

    una = llamadas[0]
    comprobar("va como multipart, no como JSON",
              "files" in una and "json" not in una, f"{sorted(una)}")
    comprobar("la referencia se llama input_image_0",
              "input_image_0" in (una.get("files") or {}),
              f"{sorted((una.get('files') or {}))}")
    comprobar("el prompt viaja en el formulario",
              (una.get("data") or {}).get("prompt") == "Allie en una cafetería",
              str(una.get("data")))
    comprobar("el token va en la cabecera",
              (una.get("headers") or {}).get("Authorization") == "Bearer ficha-de-mentira")
    comprobar("NO se pone Content-Type a mano (se perdería el boundary)",
              not any(k.lower() == "content-type" for k in (una.get("headers") or {})),
              str(una.get("headers")))
    comprobar("la cuenta va en la URL",
              "/accounts/cuenta-de-mentira/ai/run/" in una["url"], una["url"])

    # 3 · El límite que más fácil se pasa por alto: 512×512.
    enviada = (una["files"]["input_image_0"])[1]
    ref = Image.open(io.BytesIO(enviada))
    comprobar("la referencia se encoge por debajo de 512×512",
              ref.width < 512 and ref.height < 512, f"{ref.size}")
    comprobar("y no se deforma al encogerla",
              abs((ref.width / ref.height) - (1200 / 1500)) < 0.02, f"{ref.size}")

    # 4 · Si el pequeño falla, se prueba el grande en vez de rendirse.
    def pequeno_roto(modelo, kw):
        if modelo.endswith("klein-4b"):
            return Respuesta(429, {"success": False,
                                   "errors": [{"message": "out of neurons"}]},
                             '{"success":false}')
        return bien_hecha(modelo, kw)

    (datos, _, modelo), llamadas = con_post(
        pequeno_roto, lambda: cloudflare.generar(jpeg(900, 1100), "otra escena"))
    comprobar("si el pequeño falla, prueba el grande",
              bool(datos) and modelo.endswith("klein-9b"), f"{modelo} · {len(llamadas)}")

    # 5 · Si fallan los dos, se cuenta por qué en vez de reventar.
    (datos, _, motivos), _ = con_post(
        lambda m, kw: Respuesta(401, {"success": False,
                                      "errors": [{"message": "bad token"}]},
                                '{"errors":"bad token"}'),
        lambda: cloudflare.generar(jpeg(900, 1100), "otra más"))
    comprobar("si fallan todos, devuelve los motivos",
              datos is None and isinstance(motivos, list) and len(motivos) == 2,
              str(motivos)[:160])
    comprobar("y los motivos dicen algo útil",
              any("401" in m or "bad token" in m for m in (motivos or [])),
              str(motivos)[:160])

    # 6 · Una respuesta rara no debe tirar el reel.
    for nombre, r in [("un 200 sin imagen", Respuesta(200, {"success": True, "result": {}})),
                      ("algo que no es JSON", Respuesta(200, None, "<html>vaya</html>")),
                      ("la red cortada", ConnectionError("se cayó"))]:
        try:
            datos, _, motivos = con_post(lambda m, kw: r,
                                         lambda: cloudflare.generar(jpeg(600, 700), "x"))[0]
            comprobar(f"{nombre} no tumba nada", datos is None and bool(motivos),
                      str(motivos)[:120])
        except Exception as e:  # noqa: BLE001
            comprobar(f"{nombre} no tumba nada", False, f"{type(e).__name__}: {e}")

    os.environ.pop("CF_ACCOUNT_ID", None)
    os.environ.pop("CF_API_TOKEN", None)

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nel camino de Cloudflare está bien montado", flush=True)


if __name__ == "__main__":
    main()
