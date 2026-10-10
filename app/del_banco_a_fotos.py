"""Saca fotos del banco y las deja donde el reel las busca.

Por qué existe. La cuota gratuita de Hugging Face da para unas cuatro o cinco
imágenes al día y un reel necesita cuatro. Si el trabajo del banco genera y
además el del reel genera, el segundo se queda sin cuota y no sale nada. Así
que se genera UNA vez, al banco, y el reel se monta con lo que hay ahí.

Coge fotos de una misma tanda, que es lo que hace que el reel parezca un
momento y no un collage, y las marca como usadas. Si el reel no llega a
montarse, el trabajo que lo lanza las devuelve.

Deja las fotos en videos/fotos/, que es donde reel.py con SOLO_MONTAR=si las
busca, y escribe videos/del-banco.json con cuáles cogió, para poder
devolverlas.
"""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ajustes  # noqa: E402
import banco  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
FOTOS = BASE / "videos" / "fotos"
APUNTE = BASE / "videos" / "del-banco.json"

CUANTAS = ajustes.entero("FOTOS_REEL", 4)
ETIQUETA = ajustes.texto("ETIQUETA")


def log(m):
    print(f"· {m}", flush=True)


def main():
    cogidas, _ = banco.coger(CUANTAS, ETIQUETA or None)
    if not cogidas and ETIQUETA:
        log(f"No quedan libres de «{ETIQUETA}»; cojo de cualquier sitio")
        cogidas, _ = banco.coger(CUANTAS)
    if len(cogidas) < 3:
        # Devolver lo poco que haya: media tanda no da un reel, y marcarlas
        # como usadas las perdería para mañana.
        if cogidas:
            banco.devolver(cogidas)
        raise SystemExit(
            f"Solo hay {len(cogidas)} fotos libres en el banco y hacen falta 3. "
            "Mira banco/ultimo-llenado.json para ver por qué no se llenó.")

    FOTOS.mkdir(parents=True, exist_ok=True)
    for viejo in FOTOS.glob("*.jpg"):
        viejo.unlink()
    for i, origen in enumerate(cogidas, 1):
        shutil.copy(origen, FOTOS / f"foto{i}.jpg")

    APUNTE.write_text(json.dumps({
        "cuando": datetime.now(timezone.utc).isoformat(),
        "cogidas": [Path(c).name for c in cogidas],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"{len(cogidas)} fotos del banco listas para montar: "
        + ", ".join(Path(c).name for c in cogidas))


if __name__ == "__main__":
    main()
