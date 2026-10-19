"""El primer producto de pago de Allie: un pack de Halloween para imprimir.

QUÉ Y POR QUÉ. De los digitales que se venden en Halloween, los packs de
imprimibles son los que mejor encajan con lo que sabemos hacer: 3.200
búsquedas al mes en Etsy, 3-15 $, y —esto es lo que decide— NO LLEVAN TEXTO.
Las plantillas de invitación se buscan más (3.800) pero hay que escribir
dentro, y el generador de imágenes no sabe dibujar letras. Una lámina sí.

Y el calendario manda: los productos digitales son lo que se vende del 21 al
30 de octubre, cuando ya no da tiempo a enviar nada físico.

QUÉ LLEVA. Diez láminas en vertical para imprimir en A4 y cinco fondos de
móvil de regalo. Todas de la misma familia —paleta apagada, aire de papel
antiguo— porque un pack donde cada lámina va por su lado no parece un pack,
parece un cajón.

NO SALE ALLIE EN NINGUNA. Son ilustraciones, no fotos suyas: así no hay que
comprobar identidad, no hay manos que se tuerzan y el pack se puede vender
sin que dependa de que una cara salga bien.

HONESTIDAD. Las imágenes están hechas con IA y eso se dice en la ficha del
producto, no en la letra pequeña. Es lo que exige el reglamento y además es
parte de lo que se compra.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloudflare  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "producto" / "halloween"

# El hilo que une el pack. Va al final de cada orden.
ESTILO = ("vintage halloween illustration, muted autumnal palette of rust, "
          "deep plum, moss green and bone white, aged paper texture, fine "
          "ink linework, soft grain, elegant and atmospheric rather than "
          "gory, no text, no letters, no numbers, no watermark")

LAMINAS = [
    ("01-calabazas", "a still life of three heirloom pumpkins on a weathered wooden shelf"),
    ("02-gato-luna", "the silhouette of a black cat sitting before a large full moon"),
    ("03-ventana", "a gothic arched window at night with melting candles on the sill"),
    ("04-botanica", "a botanical plate of dried thistles, wheat and autumn seed pods"),
    ("05-casa-niebla", "a lonely old house on a hill wrapped in fog, seen from below"),
    ("06-murcielagos", "a flock of bats crossing a pale full moon above bare branches"),
    ("07-botica", "a shelf of old apothecary bottles with handwritten-looking labels left blank"),
    ("08-cuervo", "a raven perched on a bare branch against a heavy grey sky"),
    ("09-sendero", "a misty forest path lit by two hanging lanterns"),
    ("10-polilla", "a large moth with patterned wings against a dark botanical background"),
]

FONDOS = [
    ("f1-luna", "a full moon behind thin clouds over a dark treeline"),
    ("f2-calabaza", "a single carved pumpkin glowing softly in deep darkness"),
    ("f3-telaranas", "delicate spider webs beaded with dew against a dusk sky"),
    ("f4-velas", "three tall candles burning in the dark, warm low light"),
    ("f5-hojas", "falling autumn leaves against a deep plum night sky"),
]

# A4 en vertical y pantalla de móvil. El modelo cobra por baldosas de
# 512×512, así que estos tamaños salen por unas 160 neuronas cada uno.
MEDIDAS = {"lamina": (1024, 1448), "fondo": (1024, 1792)}
MODELO = os.environ.get("CF_MODELOS", "@cf/black-forest-labs/flux-2-klein-4b")


def log(m):
    print(f"· {m}", flush=True)


def una(nombre, descripcion, clase, referencia):
    ancho, alto = MEDIDAS[clase]
    cloudflare.ANCHO, cloudflare.ALTO = ancho, alto
    orden = f"{descripcion}. {ESTILO}"
    for intento in range(3):
        try:
            datos, seg, modelo = cloudflare.generar(
                referencia, orden, modelos=[m.strip() for m in MODELO.split(",")])
        except cloudflare.SinCupo as e:
            return None, f"sin cupo: {e}"
        except cloudflare.SinCredenciales as e:
            return None, str(e)
        if datos:
            return datos, f"{seg}s · {modelo}"
        time.sleep(3)
    return None, "no salió en tres intentos"


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    # El generador espera una imagen de partida. Como aquí no queremos a
    # Allie, se le da un lienzo liso: la orden manda y la referencia no
    # aporta cara ninguna.
    from io import BytesIO

    from PIL import Image
    b = BytesIO()
    Image.new("RGB", (512, 512), (240, 236, 228)).save(b, "JPEG")
    lienzo = b.getvalue()

    hechas = []
    for clase, lista in (("lamina", LAMINAS), ("fondo", FONDOS)):
        for nombre, descripcion in lista:
            datos, detalle = una(nombre, descripcion, clase, lienzo)
            apunte = {"nombre": nombre, "clase": clase, "detalle": detalle}
            if datos:
                f = SALIDA / f"{nombre}.jpg"
                f.write_bytes(datos)
                apunte["archivo"] = f.name
                log(f"{nombre}: hecha · {detalle}")
            else:
                log(f"{nombre}: MAL · {detalle}")
                if "cupo" in detalle:
                    hechas.append(apunte)
                    guardar(hechas)
                    log("Sin cupo: paro aquí y guardo lo que haya")
                    return
            hechas.append(apunte)
            guardar(hechas)
    log(f"{sum(1 for h in hechas if h.get('archivo'))} de {len(hechas)}")


def guardar(hechas):
    (SALIDA / "piezas.json").write_text(json.dumps(
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
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · halloween\n\n{detalle}\n",
            encoding="utf-8")
        raise
