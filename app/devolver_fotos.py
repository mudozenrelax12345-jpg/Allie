"""Devuelve al banco las fotos que se cogieron y no llegaron a publicarse.

Si el montaje del reel falla después de sacar las fotos, esas fotos quedarían
marcadas como usadas sin haber salido nunca. Costaron la cuota del día y
mañana sirven exactamente igual, así que se liberan.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import banco  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
APUNTE = BASE / "videos" / "del-banco.json"


def main():
    if not APUNTE.exists():
        print("· no se había cogido nada del banco", flush=True)
        return
    try:
        cogidas = json.loads(APUNTE.read_text(encoding="utf-8")).get("cogidas") or []
    except Exception as e:  # noqa: BLE001
        print(f"· no se pudo leer {APUNTE.name}: {e}", flush=True)
        return
    if not cogidas:
        print("· la lista estaba vacía", flush=True)
        return
    banco.devolver([banco.FOTOS / n for n in cogidas])
    APUNTE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
