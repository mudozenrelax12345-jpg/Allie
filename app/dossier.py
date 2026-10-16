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
    # Ninguna de estas pide AGARRAR. La mano apoya, sostiene por debajo o no
    # aparece. El 16 de octubre el muestrario salió con dedos de más justo
    # donde dos manos se juntaban alrededor de un objeto: ahí es donde el
    # generador se pierde, y la solución no es insistir sino no pedírselo.
    ("01-tarro-mesa",
     "a plain unbranded white ceramic cosmetic jar with a wooden lid, no label, no text",
     "the jar standing on a pale wooden table in the foreground, sharp and close to "
     "the camera; she sits behind it slightly out of focus, forearms resting on the "
     "table, hands relaxed and FLAT on the wood, fingers together and straight, "
     "looking at the camera with a soft closed-mouth smile"),
    ("02-tarro-palma",
     "a plain unbranded white ceramic cosmetic jar with a wooden lid, no label, no text",
     "the jar resting on her upturned OPEN PALM held flat at chest height, fingers "
     "straight and together, nothing gripping it, her other arm down and out of frame, "
     "looking down at the jar"),
    ("03-taza-mesa",
     "a plain unbranded matte beige stoneware mug, no label, no text",
     "the mug on a wooden table in the foreground, sharp; she leans behind it with her "
     "chin resting on the BACK of one closed hand, knuckles up, fingers curled "
     "together out of sight, looking at the camera"),
    ("04-libro-mesa",
     "a plain unbranded hardcover book with a blank linen cover, no title, no text",
     "the closed book lying flat on a table in the foreground; one hand rests FLAT on "
     "the cover, fingers straight, together and fully visible against the linen, the "
     "other arm out of frame"),
    ("05-bolsa-hombro",
     "a plain unbranded beige canvas tote bag, no print, no text",
     "the tote hanging from her shoulder by its strap, BOTH arms hanging relaxed at "
     "her sides and out of the frame below the elbow, walking down a street, looking "
     "at the camera"),
    ("06-panuelo-puesto",
     "a plain unbranded silk scarf in a solid muted colour, no pattern, no text",
     "the scarf tied loosely around her neck and draping over her shoulder, WORN not "
     "held, both hands out of frame, upper-body shot against a plain wall"),
    ("07-caja-mesa",
     "a plain unbranded square kraft cardboard gift box with a ribbon, no print",
     "the box on a table in the foreground, sharp; she sits behind it with both "
     "forearms on the table and hands FLAT on the wood either side of the box, "
     "fingers together and straight, looking at the camera"),
    ("08-frasco-detras",
     "a plain unbranded frosted glass serum bottle with a black dropper cap, no label",
     "the bottle standing on a windowsill in the foreground, sharp and backlit; she is "
     "behind it, out of focus, arms crossed loosely with hands tucked under her "
     "elbows and no fingers visible, looking at the camera"),
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
