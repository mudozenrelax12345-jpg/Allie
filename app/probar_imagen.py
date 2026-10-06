"""Pregunta a cada sitio qué deja hacer gratis HOY, y lo escribe donde se pueda leer.

No monta nada ni publica nada. Solo sirve para contestar una pregunta concreta:
¿queda alguna forma gratuita de generar una foto nueva de Allie conservando su
cara? Las dos que había dejaron de ser gratuitas y conviene saberlo con datos y
no por suposición.

El resultado se escribe en INFORME-IMAGEN.md y, además, en un aviso del
repositorio, porque los registros de GitHub Actions no se pueden leer desde fuera.
"""
import base64
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests

BASE = Path(__file__).resolve().parent.parent
REFERENCIA = "https://i.postimg.cc/023T5BJX/IMG-20261001-215255.jpg"
ESCENA = ("The same young woman from the reference photo, identical face and hair, "
          "sitting at a cafe terrace in Madrid with a coffee, upper-body shot, "
          "soft morning light, calm closed mouth, photorealistic")

lineas = []


def di(m):
    print(m, flush=True)
    lineas.append(m)


def ref():
    r = requests.get(REFERENCIA, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
    r.raise_for_status()
    return r.content


# --------------------------------------------------------------- pollinations
def pollinations():
    di("\n## Pollinations\n")
    clave = os.environ.get("POLLINATIONS_KEY", "")
    di(f"Clave en los secretos: {'sí' if clave else 'no'}")

    try:
        r = requests.get("https://image.pollinations.ai/models", timeout=60)
        modelos = r.json()
        nombres = [m if isinstance(m, str) else m.get("name", "?") for m in modelos] \
            if isinstance(modelos, list) else list(modelos)
        di(f"Modelos que anuncia: {', '.join(map(str, nombres))}")
    except Exception as e:  # noqa: BLE001
        nombres = ["flux", "turbo", "kontext"]
        di(f"No se pudo leer la lista de modelos ({type(e).__name__}); pruebo los de siempre")

    for modelo in [str(n) for n in nombres][:8]:
        for con_ref in (True, False):
            pars = {"model": modelo, "width": 768, "height": 960, "seed": 7,
                    "nologo": "true"}
            if con_ref:
                pars["image"] = REFERENCIA
            cab = {"User-Agent": "Mozilla/5.0"}
            if clave:
                cab["Authorization"] = f"Bearer {clave}"
            etiqueta = f"{modelo} {'con foto de referencia' if con_ref else 'sin referencia'}"
            try:
                r = requests.get(f"https://image.pollinations.ai/prompt/{quote(ESCENA)}",
                                 params=pars, headers=cab, timeout=240)
            except Exception as e:  # noqa: BLE001
                di(f"- {etiqueta}: no se pudo conectar ({type(e).__name__})")
                continue
            tipo = r.headers.get("content-type", "?")
            if r.status_code == 200 and tipo.startswith("image/"):
                di(f"- {etiqueta}: **FUNCIONA** · {len(r.content) // 1024} KB")
                salida = BASE / "videos" / "prueba"
                salida.mkdir(parents=True, exist_ok=True)
                seguro = etiqueta.replace(" ", "-").replace("/", "-")
                (salida / f"{seguro}.jpg").write_bytes(r.content)
            else:
                di(f"- {etiqueta}: HTTP {r.status_code} · {r.text[:120].strip()}")


# --------------------------------------------------------------- gemini
def gemini_api():
    di("\n## Gemini (la clave que ya está puesta)\n")
    clave = os.environ.get("GEMINI_API_KEY", "")
    if not clave:
        di("No hay GEMINI_API_KEY en los secretos.")
        return
    cab = {"x-goog-api-key": clave, "Content-Type": "application/json"}
    cuerpo = {"contents": [{"role": "user", "parts": [
        {"text": ESCENA},
        {"inline_data": {"mime_type": "image/jpeg",
                         "data": base64.b64encode(ref()).decode()}}]}],
              "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
    for modelo in ("gemini-3.1-flash-lite-image", "gemini-3.1-flash-image",
                   "gemini-2.5-flash-image", "gemini-3-pro-image"):
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                headers=cab, json=cuerpo, timeout=180)
            d = r.json()
        except Exception as e:  # noqa: BLE001
            di(f"- {modelo}: no se pudo conectar ({type(e).__name__})")
            continue
        if r.status_code == 200 and "error" not in d:
            di(f"- {modelo}: **FUNCIONA**")
        else:
            msg = (d.get("error") or {}).get("message", r.text[:160])
            di(f"- {modelo}: HTTP {r.status_code} · {msg[:200]}")

    # Y el texto, que es lo que de verdad usa la cuenta todos los días.
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent",
            headers=cab, json={"contents": [{"role": "user", "parts": [{"text": "di hola"}]}]},
            timeout=60)
        di(f"- texto (gemini-2.5-flash-lite): HTTP {r.status_code}"
           + ("  ← las respuestas a los fans siguen funcionando" if r.status_code == 200 else ""))
    except Exception as e:  # noqa: BLE001
        di(f"- texto: no se pudo conectar ({type(e).__name__})")


def aviso(cuerpo):
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        return
    requests.post(f"https://api.github.com/repos/{repo}/issues", timeout=60,
                  headers={"Authorization": f"Bearer {token}",
                           "Accept": "application/vnd.github+json"},
                  json={"title": "🔎 Qué queda gratis para las fotos de Allie",
                        "body": cuerpo[:60000], "labels": ["reel"]})


if __name__ == "__main__":
    di("# Qué deja hacer gratis cada sitio, hoy")
    di(f"\nFoto de referencia: {REFERENCIA}")
    for fn in (pollinations, gemini_api):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            di(f"\n(La comprobación de {fn.__name__} se rompió: {e})")
    texto = "\n".join(lineas)
    (BASE / "INFORME-IMAGEN.md").write_text(texto + "\n", encoding="utf-8")
    aviso(texto)
    print("\nEscrito en INFORME-IMAGEN.md")
    sys.exit(0)
