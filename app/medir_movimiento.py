"""Cuánto se mueve de verdad la imagen, en píxeles por segundo.

POR QUÉ NO VALE LA DIFERENCIA DE PÍXELES. El primer intento de comprobar
esto medía la diferencia media entre dos fotogramas. Parecía razonable y era
inútil: el vídeo congelado del 23 de octubre —zoom del 5 %, que Teresa
describió como «una foto quieta»— daba 17,2 sobre un umbral de 2. En una
foto con textura, mover la imagen un solo píxel ya cambia muchísimo el valor
de cada píxel. La diferencia media mide contraste, no movimiento.

LO QUE SÍ MIDE MOVIMIENTO es buscar CUÁNTO hay que desplazar un trozo de un
fotograma para que encaje con el siguiente. Eso sale en píxeles, que es la
unidad en la que el ojo juzga si algo se mueve o no.

Se mide en una franja alejada del centro, porque un zoom centrado no mueve
el centro: ahí no pasa nada por mucho que la imagen esté creciendo.
"""
import numpy as np


def desplazamiento(a, b, banda=slice(250, 420), tope=80):
    """Píxeles que hay que correr «a» en horizontal para que encaje con «b».

    Busca el desplazamiento que menos diferencia deja. Devuelve el valor
    absoluto: la dirección no importa, solo cuánto se ha movido.
    """
    fa = a[banda].astype(float)
    fb = b[banda].astype(float)
    fa = fa - fa.mean()
    fb = fb - fb.mean()
    mejor, mejor_d = None, 0
    for d in range(-tope, tope + 1):
        if d < 0:
            x, y = fa[:, -d:], fb[:, :d]
        elif d > 0:
            x, y = fa[:, :-d], fb[:, d:]
        else:
            x, y = fa, fb
        if x.shape[1] < 200:
            continue
        err = np.abs(x - y).mean()
        if mejor is None or err < mejor:
            mejor, mejor_d = err, d
    return abs(mejor_d)


def por_segundo(mp4, t0=5.0, t1=6.0, alto=slice(150, 1140)):
    """Píxeles por segundo que viaja la imagen entre dos instantes."""
    import subprocess
    import tempfile
    from pathlib import Path

    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp:
        fot = []
        for t in (t0, t1):
            p = Path(tmp) / f"{t}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(mp4),
                            "-frames:v", "1", str(p), "-y"], check=False)
            if not p.exists():
                return None
            fot.append(np.asarray(Image.open(p).convert("L")))
        recorte = [f[alto] for f in fot]
        return desplazamiento(recorte[0], recorte[1]) / max(t1 - t0, 0.001)


if __name__ == "__main__":
    import sys
    for v in sys.argv[1:]:
        print(f"{v}: {por_segundo(v):.1f} px/s")
