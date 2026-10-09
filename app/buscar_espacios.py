"""Busca en Hugging Face espacios que editen una foto conservando la cara, y
prueba cuáles contestan de verdad gratis.

Por qué hace falta. El camino bueno de Allie es un único espacio,
black-forest-labs/FLUX.1-Kontext-Dev, y ese espacio corre en ZeroGPU: cuota
diaria con cuenta y cuota por IP sin ella. Hoy se agotaron las dos y la cuenta
se quedó sin poder publicar una foto nueva. Un solo proveedor para lo único que
sabe dibujar la misma cara es el punto único de fallo de todo el proyecto.

Lo que hace. Pregunta al catálogo de espacios por los nombres que suenan a
edición con referencia, se queda con los que están encendidos, y a cada uno le
manda la foto de Allie con una escena corta. Anota el hardware (los de CPU no
tienen cuota, solo son lentos) y si devolvió imagen, con qué nombre de API y
cuánto tardó.

No decide nada ni toca el reel. Deja el informe para poder elegir con los datos
delante:
  videos/espacios/informe.json   qué contestó cada uno
  videos/espacios/<espacio>.jpg  lo que devolvió, para mirarlo
"""
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "videos" / "espacios"
INFORME = SALIDA / "informe.json"

BUSQUEDAS = ["kontext", "qwen-image-edit", "image-edit", "flux-edit",
             "nano-banana", "character-consistency"]

# Nombres de API que usan estos espacios. Varía por espacio, así que se prueban.
NOMBRES = ["/infer", "/predict", "/process", "/generate", "/run",
           "/infer_example", "/edit_image", "/chat"]

ORDEN = ("Keep her face, hair, skin tone and body exactly as they are — it must be "
         "unmistakably the same woman. Place her in this scene: The same woman, "
         "upper-body shot sitting by a window in a Madrid flat, wearing a beige knit "
         "sweater, warm autumn afternoon light, calm closed-mouth expression, hands "
         "out of frame. Photorealistic smartphone photo. No text, no logos.")

TOPE = int(os.environ.get("TOPE_ESPACIOS", "18"))
ESPERA = int(os.environ.get("ESPERA_ESPACIO", "150"))


def di(m):
    print(f"· {m}", flush=True)


def catalogo():
    """Espacios encendidos cuyo nombre suena a edición con referencia."""
    vistos, fila = {}, []
    for q in BUSQUEDAS:
        try:
            r = requests.get("https://huggingface.co/api/spaces",
                             params={"search": q, "limit": 60, "full": "true",
                                     "sort": "likes", "direction": -1},
                             timeout=60)
            r.raise_for_status()
            lote = r.json()
        except Exception as e:  # noqa: BLE001
            di(f"No pude preguntar por «{q}»: {type(e).__name__}: {e}")
            continue
        di(f"«{q}»: {len(lote)} espacios")
        for s in lote:
            ident = s.get("id")
            if not ident or ident in vistos:
                continue
            runtime = s.get("runtime") or {}
            if (runtime.get("stage") or "").upper() != "RUNNING":
                continue
            vistos[ident] = True
            fila.append({
                "espacio": ident,
                "hardware": runtime.get("hardware", {}).get("current")
                or runtime.get("hardware", {}).get("requested") or "?",
                "corazones": s.get("likes", 0),
            })
    # Primero los que no son ZeroGPU: esos no gastan cuota de nadie.
    fila.sort(key=lambda x: (("zero" in str(x["hardware"]).lower()),
                             -int(x["corazones"] or 0)))
    return fila


def referencia():
    f = SALIDA / "0-referencia.jpg"
    if f.exists():
        return f
    import yaml
    p = yaml.safe_load((BASE / "personaje.yml").read_text(encoding="utf-8"))
    r = requests.get(p["referencia_url"], headers={"User-Agent": "Mozilla/5.0"},
                     timeout=120)
    r.raise_for_status()
    f.write_bytes(r.content)
    return f


def imagen_de(resultado):
    pendientes = [resultado]
    while pendientes:
        x = pendientes.pop(0)
        if isinstance(x, (list, tuple)):
            pendientes.extend(x)
        elif isinstance(x, dict):
            pendientes.extend(x.values())
        elif isinstance(x, str) and Path(x).exists() and \
                Path(x).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            return x
    return None


def firma(cli, nombre):
    """Cómo se llaman los parámetros de esa API, para no adivinar."""
    try:
        info = cli.view_api(return_format="dict", print_info=False) or {}
    except Exception:  # noqa: BLE001
        return None
    for sitio in ("named_endpoints", "unnamed_endpoints"):
        ep = (info.get(sitio) or {}).get(nombre)
        if ep:
            return [p.get("parameter_name") or p.get("label") or ""
                    for p in (ep.get("parameters") or [])]
    return None


def probar(ficha, ident, ref):
    """(ok, detalle). Prueba los nombres de API hasta que uno devuelve imagen."""
    from gradio_client import Client, handle_file
    try:
        cli = None
        if ficha:
            for como in ("hf_token", "auth_token", "token"):
                try:
                    cli = Client(ident, verbose=False, **{como: ficha})
                    break
                except TypeError:
                    continue
        if cli is None:
            cli = Client(ident, verbose=False)
    except Exception as e:  # noqa: BLE001
        return False, f"no se pudo entrar: {type(e).__name__}: {str(e)[:200]}"

    quejas = []
    for nombre in NOMBRES:
        campos = firma(cli, nombre)
        if campos is None:
            continue
        # El parámetro de la imagen y el del texto se llaman distinto en cada
        # espacio; se busca por el nombre en vez de pasarlos por posición.
        cual_img = next((c for c in campos if re.search(
            r"image|img|photo|picture|input", str(c), re.I)), None)
        cual_txt = next((c for c in campos if re.search(
            r"prompt|text|instruction|caption", str(c), re.I)), None)
        if not cual_img or not cual_txt:
            quejas.append(f"{nombre}: no encuentro imagen+texto en {campos}")
            continue
        t0 = time.time()
        try:
            salida = cli.predict(api_name=nombre, **{
                cual_img: handle_file(str(ref)), cual_txt: ORDEN})
        except Exception as e:  # noqa: BLE001
            quejas.append(f"{nombre}: {type(e).__name__}: {str(e)[:200]}")
            continue
        ruta = imagen_de(salida)
        if not ruta:
            quejas.append(f"{nombre}: contestó sin imagen")
            continue
        destino = SALIDA / (ident.replace("/", "__") + ".jpg")
        try:
            from PIL import Image
            Image.open(ruta).convert("RGB").save(destino, "JPEG", quality=92)
        except Exception as e:  # noqa: BLE001
            quejas.append(f"{nombre}: devolvió algo que no abre: {e}")
            continue
        return True, {"api": nombre, "segundos": round(time.time() - t0, 1),
                      "parametros": {"imagen": cual_img, "texto": cual_txt},
                      "archivo": destino.name}
    return False, "; ".join(quejas) or "ninguna API encajaba"


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    ficha = os.environ.get("HF_TOKEN") or None
    ref = referencia()
    candidatos = catalogo()
    di(f"{len(candidatos)} encendidos; pruebo los {min(TOPE, len(candidatos))} primeros")

    resultados, funcionan = [], 0
    for c in candidatos[:TOPE]:
        di(f"→ {c['espacio']} ({c['hardware']}, {c['corazones']} ❤)")
        t0 = time.time()
        try:
            ok, detalle = probar(ficha, c["espacio"], ref)
        except Exception as e:  # noqa: BLE001
            ok, detalle = False, f"reventó: {type(e).__name__}: {str(e)[:200]}"
        c.update({"funciona": ok, "detalle": detalle,
                  "tardo": round(time.time() - t0, 1)})
        resultados.append(c)
        di(("   sí · " + json.dumps(detalle, ensure_ascii=False)) if ok
           else f"   no · {str(detalle)[:220]}")
        funcionan += 1 if ok else 0
        # Se escribe en cada vuelta: si el trabajo se corta por tiempo, lo
        # averiguado hasta ahí no se pierde.
        INFORME.write_text(json.dumps({
            "cuando": datetime.now(timezone.utc).isoformat(),
            "funcionan": funcionan, "probados": len(resultados),
            "resultados": resultados,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        if time.time() - t0 < 2:
            continue
    di(f"\n{funcionan} de {len(resultados)} contestaron con una imagen")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · buscar_espacios\n\n"
            f"{detalle}\n", encoding="utf-8")
        sys.exit(1)
