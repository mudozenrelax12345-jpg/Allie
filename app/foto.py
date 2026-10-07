"""Genera UNA foto suelta de Allie y la deja en videos/prueba.

Se lanza a mano desde la pestaña Actions ("Una foto suelta de Allie").
No monta vídeo y no publica nada: solo la foto, para ir probando looks.

La diferencia con reel.py es el encargo que se le manda al modelo: aquí se le
pide EXPRESAMENTE que cambie la ropa. Kontext conserva todo lo que no le digas
que cambie, y por eso Allie salía siempre con el mismo vestido verde de la
foto de referencia.
"""
import os
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import requests
import yaml
from PIL import Image
from gradio_client import Client, handle_file

BASE = Path(__file__).resolve().parent.parent
PERSONA_FILE = BASE / "personaje.yml"
SALIDA = BASE / "videos" / "prueba"
TRABAJO = BASE / ".foto"

ESPACIOS = [e.strip() for e in os.environ.get(
    "HF_ESPACIOS", "black-forest-labs/FLUX.1-Kontext-Dev").split(",") if e.strip()]

ANATOMIA = ("anatomically correct, exactly two arms and two legs, five fingers on each hand, "
            "natural human proportions, no extra limbs, no duplicated body parts, "
            "no deformed hands or feet")

CARA = ("calm closed mouth or a soft gentle smile with lips together, well-defined natural lips, "
        "no open mouth, not laughing, not talking, no visible teeth, symmetrical face, "
        "clean jawline, clear detailed eyes looking naturally, sharp focus on the face, "
        "high detail skin texture with visible pores, professional portrait photography")


def log(m):
    print(f"· {m}", flush=True)


def referencia_vertical(url):
    """La foto de Allie recortada a 4:5, que es la forma que devuelve Kontext."""
    TRABAJO.mkdir(exist_ok=True)
    r = requests.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    im = Image.open(BytesIO(r.content)).convert("RGB")
    alto = min(im.height, int(im.width * 5 / 4))
    ancho = int(alto * 4 / 5)
    x = (im.width - ancho) // 2
    y = min(max(0, (im.height - alto) // 3), im.height - alto)   # hacia la cara
    destino = TRABAJO / "referencia.jpg"
    im.crop((x, y, x + ancho, y + alto)).save(destino, "JPEG", quality=95)
    return destino


def primera_imagen(resultado):
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


def main():
    escena = os.environ.get("ESCENA", "").strip()
    outfit = os.environ.get("OUTFIT", "").strip()
    if not escena:
        raise SystemExit("Falta la escena.")
    if not outfit:
        raise SystemExit("Falta el outfit.")

    p = yaml.safe_load(PERSONA_FILE.read_text(encoding="utf-8")) or {}
    url = p.get("referencia_url")
    if not url:
        raise SystemExit("Falta 'referencia_url' en personaje.yml.")

    img = referencia_vertical(url)

    # Lo importante: la ropa SÍ cambia; la cara, el pelo y la piel no.
    orden = (
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
    log(f"Escena: {escena}")
    log(f"Outfit: {outfit}")

    ficha = os.environ.get("HF_TOKEN") or None
    if ficha:
        log("Usando HF_TOKEN (más cupo de ZeroGPU)")
    else:
        log("Sin HF_TOKEN: se entra como anónimo, el cupo es mínimo")

    dichos = []
    for espacio in ESPACIOS:
        try:
            cli = None
            if ficha:
                for como in ("hf_token", "auth_token", "token"):
                    try:
                        cli = Client(espacio, verbose=False, **{como: ficha})
                        break
                    except TypeError:
                        continue
            if cli is None:
                cli = Client(espacio, verbose=False)
            salida = cli.predict(api_name="/infer",
                                 input_image=handle_file(str(img)), prompt=orden)
        except Exception as e:  # noqa: BLE001
            dichos.append(f"{espacio}: {type(e).__name__}: {str(e)[:200]}")
            continue
        ruta = primera_imagen(salida)
        if not ruta:
            dichos.append(f"{espacio}: contestó sin imagen")
            continue
        SALIDA.mkdir(parents=True, exist_ok=True)
        sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        destino = SALIDA / f"foto-{sello}.jpg"
        Image.open(ruta).convert("RGB").save(destino, "JPEG", quality=94)
        log(f"Lista: {destino.relative_to(BASE)} ({destino.stat().st_size // 1024} KB)")
        return

    print("No ha salido la foto. Esto dijo cada sitio:", file=sys.stderr)
    for d in dichos:
        print(f"  · {d}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
