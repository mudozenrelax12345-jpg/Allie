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
    """Espacios encendidos cuyo nombre suena a edición con referencia.

    Devuelve (candidatos, cómo fue la búsqueda). Lo segundo importa tanto como
    lo primero: la primera versión de esto acabó «bien» sin probar nada porque
    la lista salió vacía, y no había manera de saber si era que Hugging Face no
    contestó, que no había resultados o que el filtro de encendidos los tiraba
    todos. Así que se cuenta cada paso.
    """
    vistos, fila, cuaderno = {}, [], []
    for q in BUSQUEDAS:
        apunte = {"busqueda": q}
        try:
            r = requests.get("https://huggingface.co/api/spaces",
                             params={"search": q, "limit": 60, "full": "true",
                                     "sort": "likes", "direction": -1},
                             timeout=60)
            apunte["http"] = r.status_code
            r.raise_for_status()
            lote = r.json()
        except Exception as e:  # noqa: BLE001
            apunte["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            di(f"«{q}»: {apunte['error']}")
            cuaderno.append(apunte)
            continue
        if not isinstance(lote, list):
            apunte["error"] = f"contestó un {type(lote).__name__}, no una lista"
            cuaderno.append(apunte)
            continue
        apunte["devueltos"] = len(lote)
        estados = {}
        for s in lote:
            ident = s.get("id")
            runtime = s.get("runtime") or {}
            estado = (runtime.get("stage") or "sin runtime").upper()
            estados[estado] = estados.get(estado, 0) + 1
            if not ident or ident in vistos:
                continue
            # Se acepta lo que esté encendido y también lo que no diga nada del
            # runtime: con que conteste la API ya vale, y mejor probar de más.
            if estado not in ("RUNNING", "SIN RUNTIME", "RUNNING_APP_STARTING"):
                continue
            vistos[ident] = True
            hw = runtime.get("hardware") or {}
            fila.append({
                "espacio": ident,
                "hardware": (hw.get("current") or hw.get("requested") or "?")
                if isinstance(hw, dict) else str(hw),
                "estado": estado,
                "corazones": s.get("likes", 0),
            })
        apunte["estados"] = estados
        di(f"«{q}»: {len(lote)} devueltos · {estados}")
        cuaderno.append(apunte)
    # Primero los que no son ZeroGPU: esos no gastan cuota de nadie.
    fila.sort(key=lambda x: (("zero" in str(x["hardware"]).lower()),
                             -int(x["corazones"] or 0)))
    return fila, cuaderno


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
    """Los parámetros de esa API con todo lo que se sabe de cada uno.

    Hace falta el componente y el valor por omisión, no solo el nombre. La
    primera versión solo mandaba imagen y texto, y seis espacios la rechazaron
    por campos que ni había mirado: lora_adapter, seed, input_image_2,
    pose_image. Y otros seis quedaron en «ninguna API encajaba» porque el
    parámetro de la imagen se llamaba de una manera que el nombre no delataba;
    el componente sí lo dice.
    """
    try:
        info = cli.view_api(return_format="dict", print_info=False) or {}
    except Exception:  # noqa: BLE001
        return None
    for sitio in ("named_endpoints", "unnamed_endpoints"):
        ep = (info.get(sitio) or {}).get(nombre)
        if ep:
            return [{
                "nombre": p.get("parameter_name") or p.get("label") or "",
                "etiqueta": p.get("label") or "",
                "componente": p.get("component") or "",
                "obligatorio": not p.get("parameter_has_default", False),
                "defecto": p.get("parameter_default"),
                "tipo": (p.get("python_type") or {}).get("type", ""),
            } for p in (ep.get("parameters") or [])]
    return None


def _es(campo, patron):
    return bool(re.search(patron, str(campo.get("nombre", "")) + " "
                          + str(campo.get("etiqueta", "")), re.I))


def relleno(campo, ref, handle_file):
    """Qué mandar en un campo obligatorio que no es la imagen ni el texto.

    Si trae valor por omisión, ese. Si no, se deduce del componente y del
    nombre: una segunda imagen es la misma referencia, una semilla es 0, y un
    desplegable se queda con su primera opción.
    """
    if not campo["obligatorio"]:
        return None, False
    if campo["defecto"] is not None:
        return campo["defecto"], True
    comp = str(campo["componente"]).lower()
    if comp in ("image", "imageeditor") or _es(campo, r"image|img|photo"):
        return handle_file(str(ref)), True
    if _es(campo, r"seed"):
        return 0, True
    if comp in ("slider", "number"):
        return 1, True
    if comp == "checkbox":
        return False, True
    if comp in ("dropdown", "radio"):
        return None, False   # sin saber las opciones, mejor no inventar
    if comp in ("textbox", "text"):
        return "", True
    return None, False


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
        # La imagen se busca primero por componente, que es lo que de verdad
        # lo dice, y solo después por el nombre. El texto, al revés: muchos
        # espacios tienen varios Textbox y solo uno es la instrucción.
        img = next((c for c in campos
                    if str(c["componente"]).lower() in ("image", "imageeditor")), None) \
            or next((c for c in campos if _es(c, r"image|img|photo|picture")), None)
        txt = next((c for c in campos
                    if _es(c, r"prompt|instruction|caption|edit")), None) \
            or next((c for c in campos
                     if str(c["componente"]).lower() in ("textbox", "text")), None)
        if not img or not txt:
            quejas.append(f"{nombre}: no encuentro imagen+texto en "
                          f"{[(c['nombre'], c['componente']) for c in campos]}")
            continue

        # Todo campo obligatorio que no sea esos dos hay que rellenarlo, o el
        # espacio rechaza la llamada antes de ejecutar nada.
        argumentos = {img["nombre"]: handle_file(str(ref)), txt["nombre"]: ORDEN}
        faltan = []
        for c in campos:
            if c["nombre"] in argumentos or not c["obligatorio"]:
                continue
            valor, sirve = relleno(c, ref, handle_file)
            if sirve:
                argumentos[c["nombre"]] = valor
            else:
                faltan.append(f"{c['nombre']}({c['componente']})")
        if faltan:
            quejas.append(f"{nombre}: no sé qué poner en {', '.join(faltan)}")
            continue

        t0 = time.time()
        try:
            salida = cli.predict(api_name=nombre, **argumentos)
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
                      "imagen": img["nombre"], "texto": txt["nombre"],
                      "extras": {k: ("<la foto>" if k == img["nombre"] else v)
                                 for k, v in argumentos.items()
                                 if k not in (img["nombre"], txt["nombre"])},
                      "archivo": destino.name}
    return False, "; ".join(quejas) or "ninguna API encajaba"


def escribir(cuaderno, candidatos, resultados, funcionan):
    INFORME.write_text(json.dumps({
        "cuando": datetime.now(timezone.utc).isoformat(),
        "busquedas": cuaderno,
        "candidatos": len(candidatos),
        "lista_candidatos": [c["espacio"] for c in candidatos],
        "funcionan": funcionan, "probados": len(resultados),
        "resultados": resultados,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    ficha = os.environ.get("HF_TOKEN") or None
    ref = referencia()
    candidatos, cuaderno = catalogo()
    # Se escribe ya, antes de probar nada: si no hay candidatos, el informe
    # tiene que decir por qué en vez de no existir.
    escribir(cuaderno, candidatos, [], 0)
    di(f"{len(candidatos)} candidatos; pruebo los {min(TOPE, len(candidatos))} primeros")
    if not candidatos:
        raise RuntimeError(
            "Ninguna búsqueda devolvió espacios utilizables; el detalle de cada "
            f"una está en videos/espacios/{INFORME.name}")

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
        escribir(cuaderno, candidatos, resultados, funcionan)
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
