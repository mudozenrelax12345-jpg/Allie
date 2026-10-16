"""Genera el muestrario de producto que se le enseña a una marca.

A diferencia de prueba_ugc.py, que buscaba DÓNDE se rompe el generador, esto
usa lo que aquella prueba encontró y solo pide composiciones que funcionan.

LA REGLA, del 16 de octubre: el generador falla cuando una sola mano agarra un
objeto pequeño y se le ven todos los dedos. Acierta cuando lo sostienen las dos
manos, cuando la mayoría de los dedos quedan detrás del producto, o cuando la
mano hace un gesto abierto en vez de agarrar. Aquí no hay ni una escena de las
que fallan: no es hacer trampa, es encuadrar como encuadra un fotógrafo de
producto, que tampoco pone una mano agarrando un bote.

Los productos son genéricos y SIN marca a propósito. Un muestrario con el
logotipo de alguien sería usar una marca que no nos ha dado permiso, y además
el generador no sabe dibujar letras.

La identidad la comprueba OpenCV en cada foto, igual que en todo lo demás: un
muestrario con dos mujeres distintas no se le puede enseñar a nadie.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402
import reel  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "dossier"
APUNTE = SALIDA / "piezas.json"

LUZ = "soft natural window light, clean uncluttered background, shallow depth of field"

# Cada pieza: (nombre, producto, composición). Las tres composiciones buenas,
# repartidas, y productos de sectores distintos para que una marca se vea
# reflejada sea del ramo que sea.
PIEZAS = [
    ("01-crema-dos-manos",
     "a plain unbranded white ceramic cosmetic jar with a wooden lid, no label, no text",
     "cradling it in BOTH hands at chest height, fingers resting flat against the jar, "
     "not gripping, looking down at it with a soft closed-mouth smile"),
    ("02-crema-senalando",
     "a plain unbranded white ceramic cosmetic jar with a wooden lid, no label, no text",
     "the jar resting on her open flat palm, her other hand pointing at it with an "
     "extended index finger, looking at the camera"),
    ("03-taza-dos-manos",
     "a plain unbranded matte beige stoneware mug, no label, no text",
     "holding it with BOTH hands wrapped around the mug at chest height, elbows on a "
     "wooden table, looking at the camera with a soft closed-mouth smile"),
    ("04-libro-apoyado",
     "a plain unbranded hardcover book with a blank linen cover, no title, no text",
     "the book resting closed on the table in front of her, one hand laid flat on top "
     "of it, fingers together, looking at the camera"),
    ("05-bolsa-hombro",
     "a plain unbranded beige canvas tote bag, no print, no text",
     "the tote hanging from her shoulder, one hand loosely through the strap with "
     "most fingers hidden behind the strap, walking, looking at the camera"),
    ("06-frasco-junto-cara",
     "a plain unbranded frosted glass serum bottle with a black dropper cap, no label",
     "holding the bottle up beside her cheek with the fingers tucked BEHIND the "
     "bottle so only the thumb and one fingertip show, looking at the camera"),
    ("07-pañuelo-dos-manos",
     "a plain unbranded folded silk scarf in a solid muted colour, no pattern, no text",
     "holding the folded scarf open with BOTH hands in front of her chest, fingers "
     "flat behind the fabric, looking down at it"),
    ("08-caja-mesa",
     "a plain unbranded square kraft cardboard gift box with a ribbon, no print",
     "the box sitting on the table, both hands resting flat on either side of it, "
     "looking at the camera with a soft closed-mouth smile"),
]

CUANTAS = int(float(os.environ.get("PIEZAS") or len(PIEZAS)))


def log(m):
    print(f"· {m}", flush=True)


def main():
    p = reel.persona()
    SALIDA.mkdir(parents=True, exist_ok=True)
    ref = reel.referencia_bytes(p)
    hechas, gasto = [], 0.0

    for nombre, producto, composicion in PIEZAS[:CUANTAS]:
        escena = (f"The same woman, upper-body shot, {composicion}. "
                  f"The product is {producto}, fully visible and in sharp focus. {LUZ}")
        apunte = {"pieza": nombre, "producto": producto, "escena": escena}
        for intento in range(3):
            try:
                datos, fallos = reel.kontext(escena, p)
            except reel.SinCuota as e:
                apunte["error"] = f"sin cuota: {e}"
                log(f"{nombre}: se agotó la cuota, paro aquí")
                hechas.append(apunte)
                guardar(hechas)
                return
            if datos is None:
                apunte.setdefault("intentos", []).append(
                    "no generó: " + " | ".join(fallos or ["?"]))
                time.sleep(3)
                continue

            # Identidad siempre, sin excepción: un muestrario con dos mujeres
            # distintas no se le enseña a nadie.
            misma, detalle = (True, "sin referencia") if ref is None \
                else gemini._identidad(ref, datos)
            if not misma:
                apunte.setdefault("intentos", []).append(f"no es ella: {detalle}")
                log(f"{nombre} intento {intento + 1}: {detalle}")
                time.sleep(2)
                continue

            f = SALIDA / f"{nombre}.jpg"
            f.write_bytes(datos)
            apunte.update({"archivo": f.name, "identidad": detalle})
            log(f"{nombre}: hecha · {detalle}")
            break
        hechas.append(apunte)
        guardar(hechas)

    log(f"{sum(1 for h in hechas if h.get('archivo'))} piezas de {len(hechas)}")


def guardar(hechas):
    APUNTE.write_text(json.dumps(
        {"cuando": datetime.now(timezone.utc).isoformat(), "piezas": hechas},
        ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · dossier\n\n{detalle}\n",
            encoding="utf-8")
        raise
