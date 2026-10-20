"""Monta una tarjeta de verdad y comprueba que se ve el texto.

Esto existe por un fallo concreto. Para que las tarjetas no se quedaran
quietas se les puso un empuje lentísimo con zoompan. Sobre una imagen fija
zoompan hace lo que se espera, pero sobre un vídeo, con d=N, saca N
fotogramas por cada uno de entrada: congela la tarjeta en su fotograma cero,
que es el de antes de que el texto entre. Resultado, once minutos de vídeo con
las tarjetas en blanco. Ni el detector de negros lo vio —el fondo no es negro
puro— ni la lista de planos, que decía exactamente lo que tenía que decir.

Lo único que lo habría visto es mirar un fotograma. Así que eso es lo que
hace esto, en quince segundos y al principio del trabajo.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import montar  # noqa: E402
import tarjetas  # noqa: E402

FICHA = {"nombre": "PRUEBA", "formato": "lista", "etiqueta": "prueba de montaje",
         "filas": [{"de": "Antes", "a": "97%", "raya": True},
                   {"de": "Despues", "a": "95%", "acento": True}]}
DUR = 5.0
MINIMO_TINTA = 0.4      # % de píxeles claros que debe haber con la tarjeta puesta


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        lienzo = tarjetas.lista(FICHA)
        for i in range(int(DUR * montar.FPS)):
            tarjetas.componer(lienzo, i / montar.FPS).save(tmp / f"f{i:04d}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-r", str(montar.FPS),
                        "-i", str(tmp / "f%04d.png"), "-c:v", "libx264",
                        "-preset", "veryfast", str(tmp / "tarjeta.mp4"), "-y"],
                       check=True)
        salida = tmp / "plano.mp4"
        montar.plano_tarjeta(tmp / "tarjeta.mp4", DUR, salida)

        medidas = []
        for t in (1.5, 3.0, 4.5):
            crudo = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(salida),
                 "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray",
                 "-s", f"{montar.W}x{montar.H}", "-"],
                capture_output=True, check=True).stdout
            img = np.frombuffer(crudo, dtype=np.uint8)
            medidas.append((t, float((img > 60).mean() * 100)))

        for t, tinta in medidas:
            print(f"  t={t}s · texto en pantalla: {tinta:.2f}%")
        peor = min(x for _, x in medidas)
        if peor < MINIMO_TINTA:
            print(f"✗ La tarjeta sale en blanco ({peor:.2f}% de tinta, hace falta "
                  f"{MINIMO_TINTA}%). El plano de tarjeta está congelando el vídeo "
                  f"en su primer fotograma.")
            sys.exit(1)

        # Y que de verdad se mueva: el primer y el último fotograma distintos.
        def fot(t):
            crudo = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(salida),
                 "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray",
                 "-s", "320x180", "-"], capture_output=True, check=True).stdout
            return np.frombuffer(crudo, dtype=np.uint8).astype(float)
        movimiento = float(np.abs(fot(1.5) - fot(4.5)).mean())
        print(f"  movimiento entre el segundo 1,5 y el 4,5: {movimiento:.2f}")
        if movimiento < 0.05:
            print("✗ La tarjeta no se mueve nada: el empuje lento no se está aplicando.")
            sys.exit(1)
    print("✓ La tarjeta se ve y se mueve")


if __name__ == "__main__":
    main()
