"""¿Toca publicar ahora? La hora que manda es la de la audiencia.

POR QUÉ NUEVA YORK Y NO MADRID. El canal está en inglés y cuenta historias
de empresas americanas: Hertz, Delta, RealPage. Quien lo ve no está en
Madrid. El pico de los Shorts está a la una de la tarde HORA DE LA
AUDIENCIA —1,28 veces lo normal, sobre 6.175 publicaciones medidas— y las
diez de la mañana de Madrid son las cuatro de la madrugada en Nueva York.

POR QUÉ DOS CRON Y UNA GUARDA. GitHub solo entiende UTC y no sabe de
cambios de hora. Entre el 25 de octubre y el 1 de noviembre, España ya ha
cambiado y Estados Unidos todavía no, así que la una de Nueva York cae un
día a las 17:00 UTC y otro a las 18:00. Se ponen los dos cron y esta guarda
deja pasar solo el que de verdad cae a la una allí.

LA VENTANA ES LA HORA ENTERA. El 19 de octubre GitHub retrasó un cron 36
minutos y una ventana de 45 lo dejó fuera por tres: ese día no se publicó
nada. No hay riesgo de publicar dos veces, porque los dos cron van
separados una hora justa y la comprobación de la hora descarta al segundo.
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

AUDIENCIA = ZoneInfo("America/New_York")


def ahora():
    return datetime.now(AUDIENCIA)


def toca(objetivo=13, margen=59, momento=None):
    m = momento or ahora()
    return m.hour == objetivo and m.minute <= margen


if __name__ == "__main__":
    objetivo = int(float(os.environ.get("HORA_OBJETIVO") or 13))
    m = ahora()
    if toca(objetivo, momento=m):
        print(f"Sí: son las {m:%H:%M} en Nueva York", flush=True)
        raise SystemExit(0)
    print(f"No: son las {m:%H:%M} en Nueva York y toca a las {objetivo}:00",
          flush=True)
    raise SystemExit(1)
