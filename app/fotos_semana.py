"""Genera VARIAS fotos de Allie y las deja subidas a una direccion publica.

Lo usa la tarea semanal: se le pasa un plan (lista de escena + outfit) y
devuelve en videos/prueba/semana.json la direccion publica de cada foto, lista
para metersela a Metricool en "media".

Una sola pasada del workflow hace todo: generar con FLUX.1 Kontext (que es lo
unico gratis que conserva la cara de Allie) y subir a un alojamiento publico.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import requests
import yaml
from PIL import Image
from gradio_client import Client, handle_file

sys.path.insert(0, str(Path(__file__).resolve().parent))
from foto import (ANATOMIA, CARA, ESPACIOS, PERSONA_FILE, SALIDA,  # noqa: E402
                  log, primera_imagen, referencia_vertical)

BASE = Path(__file__).resolve().parent.parent
INTENTOS = 3

AG = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


# ------------------------------------------------------------------ generar
def encargo(escena, outfit):
    return (
        f"Dress her in a completely different outfit: {outfit}. "
        f"The clothing in the reference photo must be entirely replaced — "
        f"do not keep the green dress or any garment from the reference. "
        f"Keep ONLY her face, hairstyle, hair colour, eye colour and skin tone exactly as "
        f"they are — it must be unmistakably the same woman. "
        f"Place her in this scene: {escena}. "
        f"{CARA}. {ANATOMIA}. "
        f"Photorealistic candid smartphone photo, soft natural daylight, upper body framing. "
        f"No text, no logos and no watermark anywhere in the image."
    )


def cliente(espacio, ficha):
    if ficha:
        for como in ("hf_token", "auth_token", "token"):
            try:
                return Client(espacio, verbose=False, **{como: ficha})
            except TypeError:
                continue
    return Client(espacio, verbose=False)


def generar(escena, outfit, img, ficha):
    """Devuelve (bytes, None) o (None, lo que dijo cada sitio)."""
    dichos = []
    for espacio in ESPACIOS:
        try:
            salida = cliente(espacio, ficha).predict(
                api_name="/infer", input_image=handle_file(str(img)),
                prompt=encargo(escena, outfit))
        except Exception as e:  # noqa: BLE001
            dichos.append(f"{espacio}: {type(e).__name__}: {str(e)[:200]}")
            continue
        ruta = primera_imagen(salida)
        if not ruta:
            dichos.append(f"{espacio}: contesto sin imagen")
            continue
        b = BytesIO()
        Image.open(ruta).convert("RGB").save(b, "JPEG", quality=94)
        return b.getvalue(), None
    return None, dichos


# ------------------------------------------------------------------ subir
def _tmpfiles(f):
    r = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f},
                      headers=AG, timeout=300)
    u = r.json().get("data", {}).get("url", "")
    return u.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)


def _envs(f):
    return requests.post("https://envs.sh", files={"file": f},
                         headers=AG, timeout=300).text.strip()


def _litterbox(f):
    return requests.post("https://litterbox.catbox.moe/resources/internals/api.php",
                         data={"reqtype": "fileupload", "time": "72h"},
                         files={"fileToUpload": f}, headers=AG, timeout=300).text.strip()


def _uguu(f):
    r = requests.post("https://uguu.se/upload", files={"files[]": f},
                      headers=AG, timeout=300)
    return r.json()["files"][0]["url"]


ALOJAMIENTOS = [("litterbox", _litterbox), ("tmpfiles", _tmpfiles),
                ("envs.sh", _envs), ("uguu", _uguu)]


def subir(ruta):
    """Sube la foto y devuelve una direccion publica que de verdad se descarga."""
    for nombre, fn in ALOJAMIENTOS:
        try:
            with open(ruta, "rb") as f:
                u = fn(f)
            if not (isinstance(u, str) and u.startswith("http")):
                log(f"  {nombre} contesto: {str(u)[:120]}")
                continue
            v = requests.get(u, headers=AG, timeout=120)
            if v.status_code == 200 and v.headers.get("content-type", "").startswith("image/"):
                log(f"  subida a {nombre}: {u}")
                return u
            log(f"  {nombre} no se descarga: HTTP {v.status_code} "
                f"{v.headers.get('content-type', '')}")
        except Exception as e:  # noqa: BLE001
            log(f"  {nombre} fallo: {type(e).__name__}: {e}")
    return None


# ------------------------------------------------------------------ main
def main():
    crudo = os.environ.get("PLAN", "").strip()
    if not crudo:
        raise SystemExit("Falta PLAN (lista JSON de {escena, outfit}).")
    try:
        plan = json.loads(crudo)
    except json.JSONDecodeError as e:
        raise SystemExit(f"PLAN no es JSON valido: {e}")
    if not isinstance(plan, list) or not plan:
        raise SystemExit("PLAN tiene que ser una lista con al menos un elemento.")
    if len(plan) > 8:
        raise SystemExit(f"PLAN trae {len(plan)} fotos; el maximo es 8 por pasada.")

    p = yaml.safe_load(PERSONA_FILE.read_text(encoding="utf-8")) or {}
    url_ref = p.get("referencia_url")
    if not url_ref:
        raise SystemExit("Falta 'referencia_url' en personaje.yml.")

    img = referencia_vertical(url_ref)
    ficha = os.environ.get("HF_TOKEN") or None
    log("Con HF_TOKEN" if ficha else "SIN HF_TOKEN: cupo anonimo, puede agotarse enseguida")

    SALIDA.mkdir(parents=True, exist_ok=True)
    sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    resultados = []

    for i, item in enumerate(plan, 1):
        escena = (item or {}).get("escena", "").strip()
        outfit = (item or {}).get("outfit", "").strip()
        log(f"[{i}/{len(plan)}] {escena[:70]}")
        if not (escena and outfit):
            resultados.append({"n": i, "error": "le falta escena u outfit"})
            continue

        datos, dichos = None, []
        for intento in range(INTENTOS):
            datos, dichos = generar(escena, outfit, img, ficha)
            if datos:
                break
            log(f"  intento {intento + 1}: " + " | ".join(dichos or []))
            time.sleep(10)

        if not datos:
            resultados.append({"n": i, "escena": escena, "outfit": outfit,
                               "error": " | ".join(dichos or ["sin imagen"])[:400]})
            continue

        destino = SALIDA / f"foto-{sello}-{i}.jpg"
        destino.write_bytes(datos)
        log(f"  generada: {destino.name} ({len(datos) // 1024} KB)")

        enlace = subir(destino)
        resultados.append({"n": i, "escena": escena, "outfit": outfit,
                           "archivo": str(destino.relative_to(BASE)),
                           "url": enlace,
                           **({} if enlace else {"error": "generada pero no se pudo subir"})})
        time.sleep(3)

    informe = {"creado": datetime.now(timezone.utc).isoformat(), "fotos": resultados}
    (SALIDA / "semana.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")

    buenas = [r for r in resultados if r.get("url")]
    log(f"Listas {len(buenas)} de {len(plan)}")
    for r in buenas:
        log(f"  URL {r['n']}: {r['url']}")
    if not buenas:
        raise SystemExit("Ninguna foto ha salido.")


if __name__ == "__main__":
    main()
