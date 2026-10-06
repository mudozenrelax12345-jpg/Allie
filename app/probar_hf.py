"""¿Se puede llamar gratis, desde un robot, a los modelos que sí conservan una cara?

Hugging Face tiene espacios públicos que ejecutan modelos de edición con foto
de referencia —FLUX.1 Kontext, Qwen-Image-Edit— y se pueden llamar por API sin
tarjeta. Si funcionan, Allie vuelve a tener fotos nuevas con su cara y sin
pagar nada.

Esto no monta ningún reel: solo pregunta y guarda lo que salga en
videos/prueba/, para poder mirarlo y decidir con la imagen delante.
"""
import shutil
import sys
import traceback
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "videos" / "prueba"
REFERENCIA = "https://i.postimg.cc/023T5BJX/IMG-20261001-215255.jpg"

ORDEN = ("Keep her face, hair and skin exactly as they are. Place her sitting at a "
         "cafe terrace in Madrid on a sunny morning, holding a coffee cup, "
         "upper-body shot, soft natural light, calm closed-mouth expression.")

# Espacios que ejecutan un modelo de edición con imagen de referencia.
ESPACIOS = [
    "black-forest-labs/FLUX.1-Kontext-Dev",
    "Qwen/Qwen-Image-Edit",
    "multimodalart/Qwen-Image-Edit-Fast",
]

lineas = []


def di(m):
    print(m, flush=True)
    lineas.append(str(m))


def referencia():
    f = SALIDA / "0-REFERENCIA.jpg"
    if not f.exists():
        r = requests.get(REFERENCIA, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
        r.raise_for_status()
        f.write_bytes(r.content)
    return f


def guardar(resultado, nombre):
    """Lo que devuelve gradio puede ser una ruta, una lista o un diccionario."""
    pendientes = [resultado]
    while pendientes:
        x = pendientes.pop(0)
        if isinstance(x, (list, tuple)):
            pendientes.extend(x)
        elif isinstance(x, dict):
            pendientes.extend(x.values())
        elif isinstance(x, str) and Path(x).exists() and Path(x).suffix.lower() in (
                ".png", ".jpg", ".jpeg", ".webp"):
            destino = SALIDA / f"{nombre}{Path(x).suffix.lower()}"
            shutil.copy(x, destino)
            return destino
    return None


def probar(espacio, img):
    from gradio_client import Client, handle_file
    di(f"\n### {espacio}")
    try:
        cli = Client(espacio, verbose=False)
    except Exception as e:  # noqa: BLE001
        di(f"- no se pudo abrir: {type(e).__name__}: {str(e)[:200]}")
        return

    try:
        api = cli.view_api(return_format="dict", print_info=False)
        puntos = list((api.get("named_endpoints") or {}).items())
        di(f"- puntos de entrada: {', '.join(n for n, _ in puntos) or '(ninguno con nombre)'}")
    except Exception as e:  # noqa: BLE001
        puntos = []
        di(f"- no se pudo leer la lista de puntos: {type(e).__name__}")

    for nombre, info in puntos:
        params = info.get("parameters") or []
        tiene_imagen = any("image" in (p.get("parameter_name") or p.get("label") or "").lower()
                           or "filepath" in str(p.get("type") or "").lower() for p in params)
        if not tiene_imagen:
            continue
        kwargs = {}
        for p in params:
            clave = p.get("parameter_name")
            if not clave:
                continue
            etiqueta = (clave + " " + str(p.get("label") or "")).lower()
            tipo = str(p.get("python_type", {}).get("type") or p.get("type") or "").lower()
            if "filepath" in tipo or "image" in etiqueta:
                kwargs[clave] = handle_file(str(img))
            elif "prompt" in etiqueta and "negative" not in etiqueta:
                kwargs[clave] = ORDEN
            elif p.get("parameter_has_default"):
                continue
            elif "str" in tipo:
                kwargs[clave] = ""
        di(f"- probando «{nombre}» con {list(kwargs)}")
        try:
            r = cli.predict(api_name=nombre, **kwargs)
        except Exception as e:  # noqa: BLE001
            di(f"  ✗ {type(e).__name__}: {str(e)[:300]}")
            continue
        destino = guardar(r, f"HF-{espacio.replace('/', '__')}")
        if destino:
            di(f"  ✓ **FUNCIONA** · guardada en {destino.name} "
               f"({destino.stat().st_size // 1024} KB)")
            return
        di(f"  ✗ contestó pero sin imagen: {str(r)[:200]}")


def aviso(cuerpo):
    import os
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        return
    requests.post(f"https://api.github.com/repos/{repo}/issues", timeout=60,
                  headers={"Authorization": f"Bearer {token}",
                           "Accept": "application/vnd.github+json"},
                  json={"title": "🔎 Modelos gratuitos que conservan la cara",
                        "body": cuerpo[:60000], "labels": ["reel"]})


if __name__ == "__main__":
    SALIDA.mkdir(parents=True, exist_ok=True)
    di("# Espacios de Hugging Face que editan una foto conservando la cara")
    img = referencia()
    for espacio in ESPACIOS:
        try:
            probar(espacio, img)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            di(f"- {espacio}: la prueba se rompió entera")
    texto = "\n".join(lineas)
    (BASE / "INFORME-HF.md").write_text(texto + "\n", encoding="utf-8")
    aviso(texto)
    sys.exit(0)
