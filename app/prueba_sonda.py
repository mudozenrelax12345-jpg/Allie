"""La sonda del cupo tiene que aguantar el momento para el que fue escrita.

QUÉ PASÓ. La sonda existía para avisar en cuanto volviera el cupo y lanzar
sola la prueba del producto. El cupo volvió la noche del 17 de octubre… y
la sonda reventó justo en ese instante con un NameError: la función que
dispara el aviso usaba `os` y `json`, y ninguno de los dos estaba
importado. Escribí el código de la celebración y no lo ejecuté ni una vez.

Resultado: ocho ejecuciones seguidas en rojo, ni una línea apuntada y una
noche entera perdida esperando una respuesta que nadie fue a buscar.

Lo que se fija aquí: que el camino del cambio de estado —el único que de
verdad importa— se recorra entero sin romperse, con y sin GITHUB_TOKEN.
"""
import importlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("CF_ACCOUNT_ID", "cuenta-de-mentira")
os.environ.setdefault("CF_API_TOKEN", "ficha-de-mentira")

import probar_cuota  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(f"{'ok  ' if bien else 'MAL '} {que}" + (f" · {detalle}" if detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


CABECERA = probar_cuota.CABECERA


def main():
    temporal = Path(tempfile.mkdtemp()) / "cuota.md"
    probar_cuota.APUNTE = temporal

    # El estado anterior era «agotado»: estamos en el momento que importa.
    temporal.write_text(
        CABECERA + "| 2026-10-17 04:35 | agotado | agotado (429) |\n",
        encoding="utf-8")

    disparos = []
    probar_cuota.estado = lambda: (True, "contestó con un modelo de prueba")
    probar_cuota.avisar_de_que_hay_cupo = lambda: disparos.append(1)

    probar_cuota.main()
    escrito = temporal.read_text(encoding="utf-8")
    comprobar("al volver el cupo se apunta la línea", "| hay |" in escrito,
              escrito.splitlines()[-1])
    comprobar("y se dispara la prueba del producto", disparos == [1],
              f"{len(disparos)} disparos")

    # Y el aviso de verdad, el que reventó: sin token tiene que avisar y
    # seguir, nunca levantar una excepción.
    importlib.reload(probar_cuota)
    probar_cuota.APUNTE = temporal
    os.environ.pop("GITHUB_TOKEN", None)
    try:
        probar_cuota.avisar_de_que_hay_cupo()
        comprobar("sin GITHUB_TOKEN no revienta", True)
    except Exception as e:  # noqa: BLE001
        comprobar("sin GITHUB_TOKEN no revienta", False, f"{type(e).__name__}: {e}")

    # Con token pero sin poder hablar con GitHub: tampoco puede reventar.
    os.environ["GITHUB_TOKEN"] = "ficha-de-mentira"
    os.environ["GITHUB_REPOSITORY"] = "nadie/ninguno"
    try:
        probar_cuota.avisar_de_que_hay_cupo()
        comprobar("si GitHub dice que no, tampoco revienta", True)
    except Exception as e:  # noqa: BLE001
        comprobar("si GitHub dice que no, tampoco revienta", False,
                  f"{type(e).__name__}: {e}")

    # Sin cambio de estado no se apunta nada: el historial no se llena de
    # líneas iguales.
    importlib.reload(probar_cuota)
    probar_cuota.APUNTE = temporal
    probar_cuota.estado = lambda: (True, "sigue habiendo")
    antes = temporal.read_text(encoding="utf-8")
    probar_cuota.main()
    comprobar("sin cambio de estado no se apunta nada",
              temporal.read_text(encoding="utf-8") == antes)

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nLa sonda aguanta el momento bueno.", flush=True)


if __name__ == "__main__":
    main()
