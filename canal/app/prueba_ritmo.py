"""Comprueba que el reparto de tiempos no deja pantallas muertas.

Los dos fallos que esto vigila llegaron los dos al vídeo montado y pasaron
dos revisiones mías, porque desde fuera un párrafo de trece segundos con una
tarjeta y una imagen parece bien repartido en la lista de planos:

  · El techo de las tarjetas no servía. El sobrante se le quitaba a la tarjeta
    topada y, si era lo único del párrafo, se le devolvía en la misma línea.
    Ocho tarjetas del vídeo 3 quedaron de ocho a diecisiete segundos quietas.

  · Una imagen que se parte en dos trozos salía dos veces seguida. Eso está
    bien si el montaje encuadra distinto cada trozo, pero si en la tirada hay
    otras imágenes es mejor alternarlas.

Se prueba el reparto solo, sin montar nada, que es donde se decide.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ritmo  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que + (f"  ·  {detalle}" if not bien and detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


def reparto(items, total, minimos, tarjetas=()):
    return ritmo.repartir(items, total, minimos, None, lambda x: x in tarjetas)


def duracion_por_nombre(salida):
    d = {}
    for n, t in salida:
        d[n] = d.get(n, 0.0) + t
    return d


def main():
    # 1 · Una tarjeta sola en un párrafo largo. No hay a quién darle el
    # sobrante, así que durará lo que dure el párrafo, pero tiene que salir
    # partida en varios planos para que el montaje la mueva.
    s = reparto(["T"], 13.0, {"T": 3.0}, tarjetas={"T"})
    comprobar("una tarjeta sola de 13s se parte en varios planos",
              len(s) >= 2, f"{s}")
    comprobar("y entre todos suman el párrafo",
              abs(sum(t for _, t in s) - 13.0) < 0.2, f"{sum(t for _,t in s):.2f}s")
    comprobar("ningún plano pasa del techo de tarjeta",
              all(t <= ritmo.TECHO_TARJETA + 0.5 for _, t in s),
              f"{max(t for _, t in s):.2f}s")

    # 2 · Tarjeta con una imagen al lado: el sobrante va a la imagen, no a la
    # tarjeta. Este es el caso que el techo tenía que resolver y no resolvía.
    s = reparto(["T", "img"], 16.0, {"T": 3.0, "img": 2.0}, tarjetas={"T"})
    por = duracion_por_nombre(s)
    comprobar("con una imagen al lado, la tarjeta se queda en su techo",
              por["T"] <= 3.0 * 1.45 + 0.6, f"la tarjeta dura {por['T']:.2f}s")
    comprobar("y el sobrante se lo lleva la imagen",
              por["img"] > por["T"], f"imagen {por['img']:.2f}s vs tarjeta {por['T']:.2f}s")

    # 3 · Dos imágenes largas se alternan en vez de ir en parejas.
    s = reparto(["a", "b"], 30.0, {"a": 2.0, "b": 2.0})
    nombres = [n for n, _ in s]
    seguidos = [(x, y) for x, y in zip(nombres, nombres[1:]) if x == y]
    comprobar("dos imágenes largas se alternan, no van en parejas",
              not seguidos, f"{nombres}")

    # 4 · Ninguna imagen se queda quieta más de su techo.
    comprobar("ninguna imagen pasa del techo de imagen",
              all(t <= ritmo.TECHO_IMAGEN + 0.5 for _, t in s),
              f"{max(t for _, t in s):.2f}s")

    # 5 · Lo corriente sigue funcionando: tres cosas en un párrafo normal.
    s = reparto(["T", "a", "b"], 18.0, {"T": 3.0, "a": 2.0, "b": 2.0}, tarjetas={"T"})
    comprobar("un párrafo normal reparte entre los tres",
              len(duracion_por_nombre(s)) == 3, f"{duracion_por_nombre(s)}")
    comprobar("y no se sale del párrafo",
              abs(sum(t for _, t in s) - 18.0) < 0.3, f"{sum(t for _,t in s):.2f}s")

    # 6 · Un párrafo corto no se parte en confeti.
    s = reparto(["T", "a"], 6.0, {"T": 2.5, "a": 2.0}, tarjetas={"T"})
    comprobar("un párrafo corto no se parte de más", len(s) == 2, f"{s}")

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nel reparto no deja pantallas muertas", flush=True)


if __name__ == "__main__":
    main()
