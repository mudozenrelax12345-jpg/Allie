"""LA PREGUNTA: ¿respeta el modelo el producto del cliente, o se lo reinventa?

De esto depende si se le puede vender algo a una marca. La promesa del
mensaje es «mándame una foto de tu producto y te hago la imagen». Si el
modelo devuelve *un* pañuelo verde en vez de *ese* pañuelo, la promesa no
se puede cumplir y hay que cambiarla antes de escribirle a nadie.

CÓMO SE MIDE. Un producto inventado a propósito para que no haya duda: un
pañuelo turquesa con borde mostaza y círculos rojos no existe, así que si
aparece en la foto es porque el modelo lo ha copiado, no porque se lo sepa.

DOS PASOS, y el primero importa. Si le diéramos el dibujo plano
directamente, estaríamos haciendo una prueba más fácil que la realidad: un
cliente manda una FOTO, con su luz, su perspectiva y su tela arrugada. Así
que primero convertimos el dibujo en una fotografía de producto, y esa foto
—no el dibujo— es la que hace de «lo que manda el cliente».

Lo que hay que mirar después, con la imagen delante y ampliada:
  · ¿están los tres colores?
  · ¿está el motivo, o se ha convertido en otra cosa?
  · ¿sigue siendo Allie?
"""
import json
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloudflare  # noqa: E402
import gemini  # noqa: E402
import reel  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "encargos"

GRANDE = ["@cf/black-forest-labs/flux-2-klein-9b"]


def log(m):
    print(f"· {m}", flush=True)


def panuelo():
    """Turquesa, borde mostaza, círculos rojos. No existe en ningún sitio."""
    im = Image.new("RGB", (900, 900), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([60, 60, 840, 840], fill=(0, 128, 128))
    d.rectangle([60, 60, 840, 840], outline=(218, 165, 32), width=55)
    for x in range(200, 801, 200):
        for y in range(200, 801, 200):
            d.ellipse([x - 55, y - 55, x + 55, y + 55], fill=(200, 30, 40))
    return a_bytes(im)


def bolso():
    """Tote partido en diagonal: granate arriba, crema abajo, aro negro."""
    im = Image.new("RGB", (900, 900), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([180, 230, 720, 820], fill=(245, 238, 220))
    d.polygon([(180, 230), (720, 230), (180, 700)], fill=(110, 30, 45))
    d.arc([300, 90, 600, 330], start=180, end=360, fill=(110, 30, 45), width=28)
    d.ellipse([400, 560, 520, 680], outline=(20, 20, 20), width=22)
    return a_bytes(im)


def a_bytes(im):
    b = BytesIO()
    im.save(b, "JPEG", quality=95)
    return b.getvalue()


ENCARGOS = [
    ("panuelo", panuelo,
     "a sharp studio photograph of this exact square silk scarf laid flat and "
     "slightly folded on a plain white table, seen from above, keeping every "
     "colour and every part of the pattern exactly as shown, no people, no text",
     "The same woman from the first image, wearing the EXACT scarf from the "
     "second image tied loosely around her neck and draping over one shoulder. "
     "Keep the scarf's colours and pattern exactly as they are in the second "
     "image — same teal ground, same wide golden border, same red circles. "
     "Upper-body shot against a plain wall, both hands out of frame, soft "
     "natural window light, looking at the camera"),
    ("bolso", bolso,
     "a sharp studio photograph of this exact canvas tote bag standing on a "
     "plain white surface, keeping every colour and shape exactly as shown, "
     "no people, no text",
     "The same woman from the first image, with the EXACT tote bag from the "
     "second image hanging from her shoulder by its strap. Keep the bag's "
     "colours and design exactly as they are in the second image — same dark "
     "red diagonal, same cream lower half, same black ring. Walking down a "
     "street, both arms out of frame below the elbow, soft natural light, "
     "looking at the camera"),
]


def generar(referencia, orden, extras=None):
    try:
        return cloudflare.generar(referencia, orden, modelos=GRANDE, extras=extras)
    except Exception as e:  # noqa: BLE001
        return None, 0, [f"{type(e).__name__}: {e}"]


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    p = reel.persona()
    allie = reel.referencia_bytes(p)
    if allie is None:
        raise RuntimeError("Sin la foto de referencia de Allie no hay prueba.")

    apuntes = []
    for nombre, dibujo, orden_foto, orden_escena in ENCARGOS:
        apunte = {"encargo": nombre}
        plano = dibujo()
        (SALIDA / f"{nombre}-0-dibujo.jpg").write_bytes(plano)

        # Paso 1 · el dibujo se convierte en la foto que mandaría un cliente.
        foto, seg, modelo = generar(plano, orden_foto)
        if foto is None:
            apunte["error"] = f"no salió la foto de producto: {modelo}"
            log(f"{nombre}: {apunte['error']}")
            apuntes.append(apunte)
            continue
        (SALIDA / f"{nombre}-1-producto.jpg").write_bytes(foto)
        apunte["producto"] = {"segundos": seg, "modelo": modelo}
        log(f"{nombre}: foto de producto hecha en {seg}s")
        time.sleep(3)

        # Paso 2 · Allie con ESE producto.
        escena, seg, modelo = generar(allie, orden_escena, extras=[foto])
        if escena is None:
            apunte["error"] = f"no salió la escena: {modelo}"
            log(f"{nombre}: {apunte['error']}")
            apuntes.append(apunte)
            continue
        (SALIDA / f"{nombre}-2-escena.jpg").write_bytes(escena)
        apunte["escena"] = {"segundos": seg, "modelo": modelo}

        misma, detalle = gemini._identidad(allie, escena)
        apunte["identidad"] = {"es_ella": bool(misma), "detalle": detalle}
        log(f"{nombre}: escena hecha en {seg}s · {detalle}")
        apuntes.append(apunte)
        guardar(apuntes)

    guardar(apuntes)
    hechas = sum(1 for a in apuntes if a.get("escena"))
    log(f"{hechas} escenas de {len(ENCARGOS)}")


def guardar(apuntes):
    (SALIDA / "prueba.json").write_text(json.dumps(
        {"cuando": datetime.now(timezone.utc).isoformat(), "encargos": apuntes},
        ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · prueba_producto\n\n"
            f"{detalle}\n", encoding="utf-8")
        raise
