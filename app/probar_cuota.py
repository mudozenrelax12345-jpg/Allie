"""¿A qué hora vuelve de verdad el cupo de Cloudflare?

EL ERROR QUE ARREGLA ESTO. Yo había dado por hecho que las 10.000 neuronas
del plan gratuito vuelven a las 00:00 UTC en punto. El 17 de octubre a las
04:33 UTC seguían agotadas sin que hubiera corrido nada desde las 21:33 del
día anterior. O sea que mi suposición era falsa, y encima estaba escrita
como si fuera un hecho comprobado.

Comprobarlo cuesta casi nada si se pregunta con un modelo de TEXTO en vez de
uno de imagen: la misma bolsa de neuronas, una fracción del gasto. Esta
sonda pregunta cada hora y apunta en un fichero del repositorio si había
cupo o no. Con un par de días de apuntes sabremos la hora de verdad en vez
de la hora que yo me creía.

Sólo escribe cuando el estado CAMBIA, para no llenar el historial de
commits iguales.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloudflare  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
APUNTE = BASE / "estado" / "cuota-cloudflare.md"

CABECERA = """# ¿A qué hora vuelve el cupo de Cloudflare?

Una sonda por hora con un modelo de texto (gasto despreciable). Apunta sólo
cuando el estado cambia: la línea que importa es la primera «hay» después de
una racha de «agotado», porque esa es la hora real del reinicio.

| cuándo (UTC) | estado | detalle |
|---|---|---|
"""


def estado():
    """(hay_cupo, detalle)."""
    try:
        texto, modelos = cloudflare.texto("Responde solo: ok")
    except cloudflare.SinCredenciales as e:
        return None, f"sin credenciales: {e}"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:120]}"
    if texto:
        return True, f"contestó con {modelos[0] if modelos else '?'}"
    dicho = " ".join(str(m) for m in (modelos or []))
    if "429" in dicho or "daily free allocation" in dicho:
        return False, "agotado (429)"
    return None, dicho[:160] or "no contestó y no dijo por qué"


def ultima_linea():
    if not APUNTE.exists():
        return ""
    lineas = [l for l in APUNTE.read_text(encoding="utf-8").splitlines()
              if l.startswith("| 2")]
    return lineas[-1] if lineas else ""


def avisar_de_que_hay_cupo():
    """Lanza sola la prueba del producto en cuanto vuelve el cupo.

    Si hay que esperar a que yo esté delante para apretar un botón, la
    respuesta llega cuando llegue. Así llega sola: la sonda de la hora en
    que vuelva el cupo dispara la prueba y deja el resultado escrito.
    """
    import urllib.error
    import urllib.request
    ficha = (os.environ.get("GITHUB_TOKEN") or "").strip()
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if not ficha or not repo:
        print("· sin GITHUB_TOKEN: no disparo nada", flush=True)
        return
    url = (f"https://api.github.com/repos/{repo}/actions/workflows/"
           f"probar-producto.yml/dispatches")
    peticion = urllib.request.Request(
        url, data=json.dumps({"ref": "main"}).encode(),
        headers={"Authorization": f"Bearer {ficha}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(peticion, timeout=60) as r:
            print(f"· prueba del producto disparada ({r.status})", flush=True)
    except urllib.error.HTTPError as e:
        print(f"· no se pudo disparar: HTTP {e.code} {e.read()[:150]}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"· no se pudo disparar: {type(e).__name__}: {e}", flush=True)


def main():
    hay, detalle = estado()
    nombre = {True: "hay", False: "agotado", None: "no se sabe"}[hay]
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    print(f"· {ahora} UTC · {nombre} · {detalle}", flush=True)

    previa = ultima_linea()
    if previa and f"| {nombre} |" in previa:
        print("· mismo estado que la vez anterior; no apunto nada", flush=True)
        return

    # El momento que estábamos esperando: de agotado a hay.
    if hay and "| agotado |" in previa:
        avisar_de_que_hay_cupo()

    APUNTE.parent.mkdir(parents=True, exist_ok=True)
    if not APUNTE.exists():
        APUNTE.write_text(CABECERA, encoding="utf-8")
    with APUNTE.open("a", encoding="utf-8") as f:
        f.write(f"| {ahora} | {nombre} | {detalle} |\n")


if __name__ == "__main__":
    main()
