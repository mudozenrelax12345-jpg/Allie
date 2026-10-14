"""Comprueba que al quitar las manos de una escena no quede una contradicción.

El 14 de octubre seis intentos seguidos se fueron a la basura con la misma
escena: «standing in a bright minimalist kitchen with hands on the counter».
El revisor la rechazaba por dedos deformes, el código reintentaba llamando a
sin_manos()... y sin_manos no reconocía «hands on the counter», porque
ninguna de sus palabras estaba en la lista. Así que dejaba la frase Y le
pegaba detrás «hands out of frame».

Un encargo que se contradice: pon las manos en la encimera y que no se vean.
El generador lo resolvía dibujando manos imposibles. Seis veces.

La regla es simple: después de sin_manos(), la escena no puede seguir
pidiendo manos.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reel  # noqa: E402

fallos = []
# Lo que no puede quedar PEDIDO en la escena (lo que añade sin_manos al
# final es otra cosa: dice que NO se vean).
PIDE_MANOS = re.compile(
    r"\b(hands? (on|in|over|against|behind|around)|holding|holds|"
    r"fingers? (on|around)|resting (her )?hands?|typing|writing)\b", re.I)

CASOS = [
    "The same woman, standing in a bright minimalist kitchen with hands on the counter",
    "The same woman, medium shot, holding a coffee cup, looking out of the window",
    "The same woman, sitting at a table, fingers around a mug, warm light",
    "The same woman, leaning on a railing, city behind her",
    "The same woman, typing on a laptop at a café table",
    "The same woman, walking down a street in autumn, smiling at the camera",
]


def main():
    for escena in CASOS:
        limpia = reel.sin_manos(escena)
        cola = limpia.split("hands out of frame")[0]
        queda = PIDE_MANOS.search(cola)
        bien = not queda
        print(("ok   " if bien else "MAL  ")
              + escena[:58]
              + ("" if bien else f"\n       queda pidiendo: «{queda.group(0)}»"
                                 f"\n       resultado: {limpia[:150]}"), flush=True)
        if not bien:
            fallos.append(escena)
        # Y que no se quede en nada: una escena vacía tampoco sirve.
        if len(limpia.split(",")) < 2:
            print(f"MAL  se quedó sin escena: {limpia}", flush=True)
            fallos.append(escena)

    if fallos:
        print(f"\n{len(fallos)} escenas se contradicen después de sin_manos",
              flush=True)
        sys.exit(1)
    print("\nninguna escena pide manos después de quitárselas", flush=True)


if __name__ == "__main__":
    main()
