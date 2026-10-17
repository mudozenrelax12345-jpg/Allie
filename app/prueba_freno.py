"""El freno del cupo: que no se pueda volver a gastar dos días en veinte minutos.

El 16 de octubre regeneré el muestrario dos veces con el modelo grande —
dieciséis imágenes de las caras — y me comí más de dos días de neuronas de
una sentada. A la mañana siguiente no había cupo ni para probar si el
generador respeta el producto de un cliente.

Esta prueba fija que:
  · por debajo del techo se llama con normalidad;
  · pasado el techo se levanta SinCupo en vez de seguir pidiendo;
  · la cuenta mira las últimas 24 horas, no el día natural, así que lo
    gastado hace dos días no cuenta y lo gastado anoche sí;
  · el apunte no guarda ni la orden ni la clave.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("CF_ACCOUNT_ID", "cuenta-de-mentira")
os.environ.setdefault("CF_API_TOKEN", "ficha-de-mentira")

import cloudflare  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(f"{'ok  ' if bien else 'MAL '} {que}" + (f" · {detalle}" if detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


def foto():
    b = BytesIO()
    Image.new("RGB", (900, 900), (180, 160, 140)).save(b, "JPEG")
    return b.getvalue()


class Respuesta:
    status_code = 500
    text = "da igual: aquí sólo se mira si se llega a llamar"

    def json(self):
        return {"success": False, "errors": ["prueba"]}


llamadas = []


def falso_post(url, **kw):
    llamadas.append(url)
    return Respuesta()


def apuntes(lineas):
    cloudflare.GASTO.write_text("\n".join(json.dumps(l) for l in lineas) + "\n",
                                encoding="utf-8")


def main():
    cloudflare.requests.post = falso_post
    temporal = Path(tempfile.mkdtemp()) / "gasto.jsonl"
    cloudflare.GASTO = temporal
    cloudflare.TECHO_NEURONAS = 9000
    ahora = datetime.now(timezone.utc)

    def linea(horas, neuronas):
        return {"cuando": (ahora - timedelta(hours=horas)).isoformat(
            timespec="seconds"), "quien": "prueba", "modelo": "x",
            "clase": "imagen", "ok": True, "segundos": 1, "neuronas": neuronas}

    # 1 · Por debajo del techo se llama.
    apuntes([linea(2, 3000)])
    llamadas.clear()
    cloudflare.generar(foto(), "una escena", modelos=["modelo-de-prueba"])
    comprobar("por debajo del techo se sigue pidiendo", len(llamadas) == 1,
              f"{len(llamadas)} llamadas")
    comprobar("y la cuenta de 24 h sale bien", cloudflare.gastado_24h() >= 3000,
              str(cloudflare.gastado_24h()))

    # 2 · Pasado el techo, ni se intenta.
    apuntes([linea(2, 6000), linea(5, 4000)])
    llamadas.clear()
    try:
        cloudflare.generar(foto(), "una escena", modelos=["modelo-de-prueba"])
        comprobar("pasado el techo se levanta SinCupo", False, "no levantó nada")
    except cloudflare.SinCupo as e:
        comprobar("pasado el techo se levanta SinCupo", True, str(e)[:60])
    comprobar("y no se llega a llamar a Cloudflare", not llamadas,
              f"{len(llamadas)} llamadas")

    # 3 · Lo de hace dos días no cuenta: es ventana, no archivo histórico.
    apuntes([linea(30, 9999), linea(48, 9999)])
    llamadas.clear()
    cloudflare.generar(foto(), "una escena", modelos=["modelo-de-prueba"])
    comprobar("lo gastado hace más de 24 h no frena nada", len(llamadas) == 1,
              f"gastado_24h={cloudflare.gastado_24h()}")

    # 4 · El apunte no guarda ni la orden ni la clave.
    temporal.write_text("", encoding="utf-8")
    cloudflare.generar(foto(), "ORDEN-SECRETA-QUE-NO-DEBE-APARECER",
                       modelos=["modelo-de-prueba"])
    escrito = temporal.read_text(encoding="utf-8")
    comprobar("el apunte no guarda la orden",
              "ORDEN-SECRETA" not in escrito, escrito[:80])
    comprobar("ni la clave", "ficha-de-mentira" not in escrito)

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nEl freno aguanta.", flush=True)


if __name__ == "__main__":
    main()
