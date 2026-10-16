"""¿Falta el reel de hoy? Deja la respuesta donde el workflow pueda leerla.

Esto evita un bloqueo que descubrí el 11 de octubre y que habría dejado la
cuenta sin publicar indefinidamente sin que nadie entendiera por qué.

La ventana de cuota de Hugging Face dura 24 horas desde la PRIMERA llamada
que la abre, así que su hora no es fija: se mueve al momento en que se generó
el día anterior. Ayer se generó a las 15:26 UTC, o sea que hoy no hay cuota
hasta las 15:26. El reel diario estaba puesto a las 05:40, que es siempre
antes. Y ahí está la trampa: si el único intento del día cae antes de que
abra la ventana, nunca se genera nada, la ventana nunca se vuelve a anclar, y
mañana pasa exactamente lo mismo. Un trabajo diario que falla todos los días
para siempre.

La salida es intentarlo varias veces repartidas por el día y parar en cuanto
uno salga bien. Esto es lo que decide si un intento tiene algo que hacer:
responde "si" solo si hoy todavía no hay reel.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ULTIMO = BASE / "videos" / "ultimo.json"


def falta():
    if not ULTIMO.exists():
        return True, "no hay ningún reel guardado"
    try:
        d = json.loads(ULTIMO.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return True, f"ultimo.json no se puede leer ({e})"
    cuando = d.get("creado") or d.get("cuando") or ""
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if str(cuando)[:10] == hoy:
        return False, f"ya hay reel de hoy ({cuando})"
    return True, f"el último reel es de {str(cuando)[:10] or 'fecha desconocida'}"


def main():
    # Forzar, para rehacer el reel del día cuando el que hay no sirve: salió
    # mudo, salió con una foto mala, o se acaba de arreglar algo y hay que
    # comprobarlo. Sin esto, la única forma de reintentar era esperar a
    # mañana.
    if (os.environ.get("FORZAR") or "").strip().lower() in ("si", "sí", "true", "1"):
        hace_falta, porque = True, "forzado a mano"
    else:
        hace_falta, porque = falta()
    print(f"· {'hace falta' if hace_falta else 'no hace falta'}: {porque}", flush=True)
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"falta={'si' if hace_falta else 'no'}\n")
            f.write(f"porque={porque}\n")


if __name__ == "__main__":
    main()
