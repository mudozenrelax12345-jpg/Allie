"""¿Son las diez en Madrid?

EL PROBLEMA. Los relojes de GitHub Actions van en UTC y no entienden de
husos. La publicación está puesta a las «10:12» con un cron a las 08:12 UTC,
que efectivamente son las 10:12 en Madrid… hasta el último domingo de
octubre. Ese día España atrasa el reloj y el mismo cron pasa a dispararse a
las 09:12 de la mañana, una hora antes de la hora punta, sin que nada falle
ni nadie se entere. Y en marzo, al revés.

Las 10:00 son la hora punta de la audiencia de Allie los SIETE días de la
semana, así que publicar a las nueve es tirar la mitad del alcance por un
detalle de husos horarios.

LA SOLUCIÓN. Dos crons, uno a cada lado del cambio, y esta guarda decide
cuál de los dos sigue adelante. El otro se para en el primer paso sin tocar
nada. Es feo y es el único modo: GitHub no admite huso en el cron.
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")


def ahora():
    return datetime.now(MADRID)


def toca(objetivo=10, margen=45, momento=None):
    """¿Estamos dentro de la ventana de la hora objetivo, en Madrid?

    `margen` en minutos: GitHub retrasa los crons cuando va cargado, a veces
    veinte minutos o más, así que la ventana no puede ser estrecha. Pero
    tampoco de una hora, o pasarían los dos crons y publicaríamos dos veces,
    que es exactamente el fallo que hunde una de las dos piezas.
    """
    m = momento or ahora()
    return m.hour == objetivo and m.minute <= margen


if __name__ == "__main__":
    objetivo = int(float(os.environ.get("HORA_OBJETIVO") or 10))
    m = ahora()
    bien = toca(objetivo)
    print(f"· en Madrid son las {m:%H:%M} del {m:%d/%m} · objetivo {objetivo}:00 · "
          f"{'adelante' if bien else 'no toca, me paro'}", flush=True)
    # Para GitHub Actions: deja la respuesta donde el workflow pueda leerla.
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"toca={'si' if bien else 'no'}\n")
    sys.exit(0)
