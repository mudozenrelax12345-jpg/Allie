"""¿Por dónde más se pueden sacar fotos de Allie, gratis y con su cara?

EL PROBLEMA. El 17 de octubre el cupo de Cloudflare estaba agotado a las
04:35 UTC y seguía agotado a las 10:30, sin que hubiera corrido nada entre
medias. Con un solo proveedor, un día así es un día sin fotos y sin poder
atender a un cliente. La respuesta no es insistirle a Cloudflare: es tener
más de una puerta, como ya se hizo con la identidad (OpenCV en vez de
Gemini) y con el texto.

QUÉ PRUEBA. Cada candidato recibe LO MISMO: la foto de Allie, la foto de un
producto inventado y la orden de ponerla con ese producto. Así se contesta
de una vez a las dos preguntas que importan:

  1. ¿sale Allie, o sale otra mujer?
  2. ¿sale ESE producto, o uno parecido?

La segunda es la que decide si se le puede vender algo a una marca.

Si un candidato falla con dos imágenes, se reintenta con una sola: puede que
sepa copiar una cara y no sepa manejar dos referencias, y eso también es un
resultado útil.

NO SE ESCRIBE NINGUNA CLAVE en el informe. Sólo si estaba puesta o no.
"""
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloudflare  # noqa: E402
import gemini  # noqa: E402
import reel  # noqa: E402
from prueba_producto import panuelo  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "salidas"
INFORME = SALIDA / "informe.md"

POLLI = "https://gen.pollinations.ai/v1/images/edits"
GEMINI_IMG = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "{modelo}:generateContent")

ORDEN = (
    "The same woman as in the first image — keep her face, hair and skin tone "
    "exactly, it must be unmistakably the same person. She is wearing the exact "
    "scarf from the second image tied loosely around her neck: same teal ground, "
    "same wide golden border, same red circles, unchanged. Upper-body "
    "photograph against a plain wall, both hands out of frame, soft natural "
    "window light, looking at the camera. No text, no logos, no watermark.")

ORDEN_SOLA = (
    "The same woman as in the image — keep her face, hair and skin tone exactly. "
    "Upper-body photograph against a plain wall, both hands out of frame, soft "
    "natural window light, looking at the camera. No text, no logos, no watermark.")


def log(m):
    print(f"· {m}", flush=True)


def encoge(datos, lado=1024):
    from PIL import Image
    im = Image.open(BytesIO(datos)).convert("RGB")
    im.thumbnail((lado, lado))
    b = BytesIO()
    im.save(b, "JPEG", quality=92)
    return b.getvalue()


# ------------------------------------------------------------- candidatos
def por_cloudflare(allie, producto, orden):
    if not cloudflare.hay():
        return None, "sin credenciales de Cloudflare"
    datos, seg, modelo = cloudflare.generar(
        allie, orden, modelos=["@cf/black-forest-labs/flux-2-klein-4b"],
        extras=[producto] if producto else None)
    if datos:
        return datos, f"{seg}s"
    return None, " | ".join(str(m) for m in (modelo or []))[:300]


def _polli(modelo, allie, producto, orden):
    clave = (os.environ.get("POLLINATIONS_KEY") or "").strip()
    if not clave:
        return None, "sin POLLINATIONS_KEY"
    ficheros = [("image", ("allie.jpg", allie, "image/jpeg"))]
    if producto:
        ficheros.append(("image", ("producto.jpg", producto, "image/jpeg")))
    t0 = time.time()
    try:
        r = requests.post(POLLI, headers={"Authorization": f"Bearer {clave}"},
                          files=ficheros,
                          data={"prompt": orden, "model": modelo,
                                "size": "1024x1280", "response_format": "b64_json"},
                          timeout=300)
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:200]}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code} · {r.text[:250]}"
    try:
        cuerpo = r.json()
        trozo = (cuerpo.get("data") or [{}])[0]
        b64 = trozo.get("b64_json")
        if not b64:
            return None, f"sin imagen · {str(cuerpo)[:200]}"
        return base64.b64decode(b64), f"{round(time.time() - t0, 1)}s"
    except Exception as e:  # noqa: BLE001
        return None, f"respuesta rara · {type(e).__name__}: {str(e)[:150]}"


def por_gemini_imagen(modelo, allie, producto, orden):
    clave = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not clave:
        return None, "sin GEMINI_API_KEY"
    partes = [{"text": orden},
              {"inline_data": {"mime_type": "image/jpeg",
                               "data": base64.b64encode(allie).decode()}}]
    if producto:
        partes.append({"inline_data": {"mime_type": "image/jpeg",
                                       "data": base64.b64encode(producto).decode()}})
    t0 = time.time()
    try:
        r = requests.post(GEMINI_IMG.format(modelo=modelo),
                          headers={"x-goog-api-key": clave},
                          json={"contents": [{"parts": partes}]}, timeout=300)
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:200]}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code} · " + " ".join(r.text.split())[:1200]
    try:
        for p in r.json()["candidates"][0]["content"]["parts"]:
            dato = p.get("inline_data") or p.get("inlineData")
            if dato and dato.get("data"):
                return base64.b64decode(dato["data"]), f"{round(time.time() - t0, 1)}s"
        return None, f"contestó sin imagen · {str(r.json())[:200]}"
    except Exception as e:  # noqa: BLE001
        return None, f"respuesta rara · {type(e).__name__}: {str(e)[:150]}"


PERSONA = None

MODELSCOPE = "https://api-inference.modelscope.cn/v1"


def por_modelscope(modelo):
    """ModelScope (Alibaba): 200 monedas al día de regalo, una por imagen.

    Trabaja con la URL pública de la foto de Allie, no con el fichero: el
    repositorio es público, así que la dirección ya existe. Va por tareas:
    se pide, devuelve un identificador y se pregunta cada pocos segundos.
    """
    def hacer(allie, producto, orden):
        clave = (os.environ.get("MODELSCOPE_TOKEN") or "").strip()
        if not clave:
            return None, "sin MODELSCOPE_TOKEN"
        if producto:
            return None, "de momento sólo se le pasa una referencia"
        url_allie = (PERSONA or {}).get("referencia_url")
        if not url_allie:
            return None, "no hay URL pública de la referencia"
        cab = {"Authorization": f"Bearer {clave}"}
        t0 = time.time()
        try:
            r = requests.post(
                f"{MODELSCOPE}/images/generations",
                headers={**cab, "Content-Type": "application/json",
                         "X-ModelScope-Async-Mode": "true"},
                json={"model": modelo, "prompt": orden, "image_url": url_allie},
                timeout=120)
        except Exception as e:  # noqa: BLE001
            return None, f"{type(e).__name__}: {str(e)[:180]}"
        if r.status_code not in (200, 201):
            return None, f"HTTP {r.status_code} · {r.text[:220]}"
        tarea = (r.json() or {}).get("task_id")
        if not tarea:
            return None, f"sin task_id · {r.text[:200]}"
        for _ in range(40):
            time.sleep(6)
            try:
                e = requests.get(f"{MODELSCOPE}/tasks/{tarea}",
                                 headers={**cab,
                                          "X-ModelScope-Task-Type": "image_generation"},
                                 timeout=60).json()
            except Exception as ex:  # noqa: BLE001
                return None, f"preguntando por la tarea: {type(ex).__name__}: {ex}"
            estado = (e.get("task_status") or "").upper()
            if estado == "SUCCEED":
                fotos = e.get("output_images") or []
                if not fotos:
                    return None, f"acabó sin imagen · {str(e)[:180]}"
                try:
                    return (requests.get(fotos[0], timeout=120).content,
                            f"{round(time.time() - t0, 1)}s")
                except Exception as ex:  # noqa: BLE001
                    return None, f"no se pudo bajar: {ex}"
            if estado in ("FAILED", "CANCELED"):
                return None, f"{estado} · {str(e)[:200]}"
        return None, "la tarea no acabó en cuatro minutos"
    return hacer


def por_hugging_face(allie, producto, orden):
    """La puerta vieja. reel.kontext() prueba Cloudflare primero, así que se
    le esconden las credenciales durante la llamada para que vaya derecho a
    Hugging Face. No sabe manejar dos referencias: va sólo con Allie."""
    if producto:
        return None, "no admite dos referencias; se prueba sólo con Allie"
    guarda = {}
    for n in cloudflare.NOMBRES_CUENTA + cloudflare.NOMBRES_FICHA:
        if n in os.environ:
            guarda[n] = os.environ.pop(n)
    t0 = time.time()
    try:
        datos, dichos = reel.kontext(
            "upper-body photograph against a plain wall, soft natural window "
            "light, both hands out of frame, looking at the camera", PERSONA)
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        os.environ.update(guarda)
    if datos:
        return datos, f"{round(time.time() - t0, 1)}s"
    return None, " | ".join(str(d) for d in (dichos or []))[:300]


CANDIDATOS = [
    ("cloudflare-klein4b", por_cloudflare),
    ("hugging-face", por_hugging_face),
    ("polli-klein4b", lambda a, p, o: _polli("black-forest-labs/flux.2-klein-4b", a, p, o)),
    ("polli-gemini-image", lambda a, p, o: _polli("google/gemini-2.5-flash-image", a, p, o)),
    ("polli-kontext-pro", lambda a, p, o: _polli("black-forest-labs/flux.1-kontext-pro", a, p, o)),
    ("polli-seedream4", lambda a, p, o: _polli("bytedance/seedream-4.0", a, p, o)),
    ("gemini-directo", lambda a, p, o: por_gemini_imagen("gemini-2.5-flash-image", a, p, o)),
    ("modelscope-qwen-edit", por_modelscope("Qwen/Qwen-Image-Edit-2511")),
    ("modelscope-qwen-edit-v1", por_modelscope("Qwen/Qwen-Image-Edit")),
]


def main():
    global PERSONA
    SALIDA.mkdir(parents=True, exist_ok=True)
    p = PERSONA = reel.persona()
    allie = reel.referencia_bytes(p)
    if allie is None:
        raise RuntimeError("Sin la foto de referencia de Allie no hay nada que probar.")
    allie = encoge(allie)
    producto = encoge(panuelo(), 768)
    (SALIDA / "00-producto.jpg").write_bytes(producto)

    filas = []
    for nombre, hacer in CANDIDATOS:
        fila = {"candidato": nombre}
        datos, dicho = hacer(allie, producto, ORDEN)
        fila["con_producto"] = dicho
        if datos is None:
            log(f"{nombre}: con producto, no · {dicho}")
            # Puede saber copiar una cara y no saber con dos referencias.
            datos, dicho2 = hacer(allie, None, ORDEN_SOLA)
            fila["solo_allie"] = dicho2
            fila["cual"] = "solo-allie" if datos else None
            if datos is None:
                log(f"{nombre}: sola tampoco · {dicho2}")
                filas.append(fila)
                guardar(filas)
                continue
        else:
            fila["cual"] = "con-producto"

        f = SALIDA / f"{nombre}-{fila['cual']}.jpg"
        f.write_bytes(datos)
        fila["archivo"] = f.name
        try:
            misma, detalle = gemini._identidad(allie, datos)
            fila["identidad"] = f"{'sí' if misma else 'NO'} · {detalle}"
        except Exception as e:  # noqa: BLE001
            fila["identidad"] = f"no se pudo comprobar: {e}"
        log(f"{nombre}: salió ({fila['cual']}) · {fila['identidad']}")
        filas.append(fila)
        guardar(filas)

    guardar(filas)
    buenos = [f["candidato"] for f in filas if f.get("archivo")]
    log(f"funcionan {len(buenos)} de {len(CANDIDATOS)}: {', '.join(buenos) or 'ninguno'}")


def guardar(filas):
    lineas = [
        "# Por dónde se pueden sacar fotos de Allie",
        "",
        f"Prueba del {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Todos reciben "
        "lo mismo: la foto de Allie, un pañuelo inventado y la orden de ponérselo.",
        "",
        "| candidato | con producto | sólo Allie | ¿es ella? | archivo |",
        "|---|---|---|---|---|",
    ]
    for f in filas:
        lineas.append("| {} | {} | {} | {} | {} |".format(
            f.get("candidato", ""),
            str(f.get("con_producto", ""))[:110].replace("|", "/"),
            str(f.get("solo_allie", "—"))[:70].replace("|", "/"),
            f.get("identidad", "—"), f.get("archivo", "—")))
    INFORME.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    (SALIDA / "informe.json").write_text(
        json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · probar_salidas\n\n"
            f"{detalle}\n", encoding="utf-8")
        raise
