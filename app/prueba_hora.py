"""Que el cambio de hora de octubre no mueva la publicación a las nueve.

El 25 de octubre España atrasa el reloj. El cron de las 08:12 UTC, que hoy
son las 10:12 de Madrid, pasa a ser las 09:12: una hora antes de la hora
punta, sin que falle nada ni salte ningún aviso. Es el tipo de fallo que no
se descubre hasta que alguien mira las métricas tres semanas después.

Esta prueba recorre los dos crons —el de verano y el de invierno— a cada
lado del cambio, y comprueba que CADA DÍA pasa exactamente uno.
"""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hora  # noqa: E402

UTC = ZoneInfo("UTC")
fallos = []


def comprobar(que, bien, detalle=""):
    print(f"{'ok  ' if bien else 'MAL '} {que}" + (f" · {detalle}" if detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


def en_madrid(ano, mes, dia, h_utc, m_utc):
    return datetime(ano, mes, dia, h_utc, m_utc, tzinfo=UTC).astimezone(hora.MADRID)


def main():
    # Los dos crons que vamos a poner: 08:12 y 09:12 UTC.
    crons = [(8, 12), (9, 12)]

    # Una semana a cada lado del cambio de hora del 25 de octubre de 2026.
    for dia in (18, 19, 20, 24, 25, 26, 27, 31):
        pasan = [c for c in crons if hora.toca(10, momento=en_madrid(2026, 10, dia, *c))]
        locales = [f"{en_madrid(2026, 10, dia, *c):%H:%M}" for c in crons]
        comprobar(f"el {dia} de octubre pasa exactamente un cron",
                  len(pasan) == 1, f"en Madrid serían las {' y las '.join(locales)}")

    # Y en pleno invierno y pleno verano.
    for ano, mes, dia in ((2026, 12, 15), (2027, 3, 29), (2027, 7, 1)):
        pasan = [c for c in crons if hora.toca(10, momento=en_madrid(ano, mes, dia, *c))]
        comprobar(f"el {dia}/{mes}/{ano} pasa exactamente un cron", len(pasan) == 1,
                  f"{[f'{en_madrid(ano, mes, dia, *c):%H:%M}' for c in crons]}")

    # La ventana no puede ser tan ancha que pasen los dos.
    comprobar("a las 10:50 ya no toca", not hora.toca(
        10, momento=datetime(2026, 10, 20, 10, 50, tzinfo=hora.MADRID)))
    comprobar("a las 10:05 sí toca", hora.toca(
        10, momento=datetime(2026, 10, 20, 10, 5, tzinfo=hora.MADRID)))
    comprobar("a las 09:59 no toca", not hora.toca(
        10, momento=datetime(2026, 10, 20, 9, 59, tzinfo=hora.MADRID)))

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nLa publicación aguanta el cambio de hora.", flush=True)


if __name__ == "__main__":
    main()
