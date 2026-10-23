"""Una hoja de contactos con las candidatas de Commons para un término.

POR QUÉ EXISTE. Tres intentos seguidos de acertar con la foto del templo de
Debod, y los tres malos: una nevada con un músico delante, un primer plano
del reflejo donde no se ve el templo, y un «atardecer DESDE el templo de
Debod» que es una puesta de sol sin templo. Las tres las elegí leyendo el
nombre del fichero.

Por el nombre no se puede. «Atardecer desde el Templo de Debod» y
«Atardecer en el Templo de Debod» se escriben casi igual y son fotos
completamente distintas. La única forma de elegir una foto es verla.

Esto baja las primeras candidatas de un término, las pega en una rejilla
numerada y deja la imagen donde se pueda mirar. Luego se fija la buena en
contenido/cola.json con «File:loquesea.jpg».

Cuesta una ejecución y ahorra tres.
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
BASE = Path(__file__).resolve().parent.parent
DESTINO = BASE / "video" / "candidatas"

import lugares  # noqa: E402

CELDA_W, CELDA_H, COLS = 520, 390, 3


def main():
    termino = (os.environ.get("TERMINO") or " ".join(sys.argv[1:])).strip()
    if not termino:
        raise SystemExit("Hace falta un término de búsqueda.")
    cuantas = int(os.environ.get("CUANTAS") or 9)

    DESTINO.mkdir(parents=True, exist_ok=True)
    for v in DESTINO.glob("*"):
        v.unlink()

    cand = lugares.buscar(termino)[:cuantas]
    if not cand:
        raise SystemExit(f"Ninguna candidata libre para «{termino}».")

    from PIL import Image, ImageDraw, ImageFont
    fuente = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 21)
    filas = (len(cand) + COLS - 1) // COLS
    hoja = Image.new("RGB", (CELDA_W * COLS, CELDA_H * filas), (18, 18, 20))
    d = ImageDraw.Draw(hoja)

    for i, c in enumerate(cand):
        ruta = DESTINO / f"{i:02d}.jpg"
        try:
            lugares.bajar(c["url"], ruta)
            im = Image.open(ruta).convert("RGB")
        except Exception as e:  # noqa: BLE001
            print(f"· {i}: no baja ({e})", flush=True)
            continue
        e_ = max(CELDA_W / im.width, (CELDA_H - 42) / im.height)
        im = im.resize((int(im.width * e_), int(im.height * e_)), Image.LANCZOS)
        cx = (im.width - CELDA_W) // 2
        im = im.crop((cx, 0, cx + CELDA_W, min(im.height, CELDA_H - 42)))
        x, y = (i % COLS) * CELDA_W, (i // COLS) * CELDA_H
        hoja.paste(im, (x, y + 42))
        d.rectangle([x, y, x + CELDA_W, y + 42], fill=(18, 18, 20))
        nombre = c["titulo"][5:]
        d.text((x + 10, y + 9), f"{i}  {nombre[:40]}", font=fuente, fill=(245, 245, 245))
        print(f"· {i} · {c['titulo'][5:]} · {c['licencia']} · "
              f"{c['ancho']}×{c['alto']}", flush=True)

    salida = BASE / "video" / "candidatas.jpg"
    hoja.save(salida, "JPEG", quality=88)
    print(f"\nHoja en {salida}", flush=True)
    subprocess.run(["ls", "-la", str(salida)], check=False)


if __name__ == "__main__":
    main()
