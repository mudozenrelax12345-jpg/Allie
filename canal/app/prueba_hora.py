"""Que pase exactamente un cron al día, y en la semana rara también.

LA SEMANA RARA. España cambia la hora el 25 de octubre y Estados Unidos el
1 de noviembre. Entre esos dos domingos hay una semana en que la una de la
tarde de Nueva York cae en una hora UTC distinta a la del resto del año.
Si los dos cron pasaran ese día, se publicarían dos Shorts seguidos; si no
pasara ninguno, se perdería el día. Esto exige que pase uno y solo uno.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hora  # noqa: E402

# Los dos cron del flujo, en UTC.
CRONES = [(17, 5), (18, 5)]

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que + (f" · {detalle}" if detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


def main():
    # Un año entero, día a día: nunca dos, nunca ninguno.
    dia = datetime(2026, 10, 1, tzinfo=timezone.utc)
    fin = datetime(2027, 10, 1, tzinfo=timezone.utc)
    dobles, ceros = [], []
    while dia < fin:
        pasan = [c for c in CRONES
                 if hora.toca(13, momento=datetime(dia.year, dia.month, dia.day,
                                                   c[0], c[1], tzinfo=timezone.utc)
                              .astimezone(hora.AUDIENCIA))]
        if len(pasan) > 1:
            dobles.append(dia.date())
        if not pasan:
            ceros.append(dia.date())
        dia += timedelta(days=1)

    comprobar("ningún día pasan los dos cron", not dobles,
              f"{len(dobles)} días: {dobles[:3]}")
    comprobar("ningún día se queda sin publicar", not ceros,
              f"{len(ceros)} días: {ceros[:3]}")

    # Y la semana rara, nombrada, por si algún día alguien la toca.
    for d in (28, 29, 30):
        pasan = [c for c in CRONES
                 if hora.toca(13, momento=datetime(2026, 10, d, c[0], c[1],
                                                   tzinfo=timezone.utc)
                              .astimezone(hora.AUDIENCIA))]
        comprobar(f"el {d}/10/2026 (España ya cambió, EE. UU. no) pasa uno",
                  len(pasan) == 1, f"pasaron {len(pasan)}")

    # La ventana es la hora entera: un cron retrasado media hora sigue valiendo.
    y = hora.AUDIENCIA
    comprobar("a las 13:50 de Nueva York todavía toca",
              hora.toca(13, momento=datetime(2026, 11, 10, 13, 50, tzinfo=y)))
    comprobar("a las 14:00 ya no toca",
              not hora.toca(13, momento=datetime(2026, 11, 10, 14, 0, tzinfo=y)))
    comprobar("a las 12:59 todavía no toca",
              not hora.toca(13, momento=datetime(2026, 11, 10, 12, 59, tzinfo=y)))

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nun cron al día, todo el año", flush=True)


if __name__ == "__main__":
    main()
