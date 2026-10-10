"""Comprueba que el revisor distingue a Allie de otra mujer.

Esta prueba tiene respuestas conocidas porque las miré a mano el 10 de
octubre, ampliando las caras y comparándolas con la referencia:

  20261009-1439-1.jpg   SÍ es Allie: rubia clara, ojos verdes.
  20261009-1439-2.jpg   NO es Allie: pelo castaño ceniza, cejas mucho más
                        marcadas, ojos oscuros. El revisor de calidad la
                        había aprobado y se programó en un carrusel.
  20261009-1439-4.jpg   Dudosa: ojos verdes pero pelo castaño con mechas.
                        No se exige un resultado concreto; solo se informa.

El caso que importa es el segundo. Mientras el revisor solo miraba manos y
dientes, una foto de otra mujer bien hecha pasaba sin problema, y eso es
exactamente lo que hundió la cuenta: una semana publicando a una desconocida.

Sin GEMINI_API_KEY no se puede comprobar nada, así que la prueba se salta en
vez de fallar: en los trabajos que sí llevan clave, se ejecuta.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402
import reel  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
FOTOS = BASE / "banco" / "fotos"

CASOS = [
    ("20261009-1439-1.jpg", True, "rubia de ojos verdes, es ella"),
    ("20261009-1439-2.jpg", False, "castaña de ojos oscuros, no es ella"),
]


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("· sin GEMINI_API_KEY: me salto la comprobación de identidad", flush=True)
        return
    p = reel.persona()
    ref = reel.referencia_bytes(p)
    if ref is None:
        print("· no se pudo traer la referencia: me salto la comprobación", flush=True)
        return

    fallos = []
    for nombre, esperado, porque in CASOS:
        f = FOTOS / nombre
        if not f.exists():
            print(f"· falta {nombre}, me la salto", flush=True)
            continue
        ok, problema = gemini.revisar_imagen(f.read_bytes(), ref)
        bien = ok == esperado
        print(("ok   " if bien else "MAL  ")
              + f"{nombre} ({porque}) → {'pasa' if ok else 'descartada'}"
              + (f" · {problema}" if problema else ""), flush=True)
        if not bien:
            fallos.append(nombre)

    if fallos:
        print(f"\nEl revisor no distingue a Allie en: {', '.join(fallos)}.", flush=True)
        print("Publicar a otra mujer en su cuenta es el fallo más caro que "
              "tiene este proyecto; no sigo.", flush=True)
        sys.exit(1)
    print("\nel revisor distingue a Allie", flush=True)


if __name__ == "__main__":
    main()
