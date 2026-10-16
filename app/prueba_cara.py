"""Comprueba, con fotos de verdad, que la comprobación de cara distingue a Allie.

Esta prueba no usa casos inventados: usa las fotos que están en el
repositorio, incluida la que de verdad se publicó durante una semana siendo
otra mujer (videos/prueba/sana-sin-referencia.jpg, generada sin la foto de
referencia). Si un día la comprobación deja de distinguirlas, esto se pone
rojo antes de que se publique nada.

Lo que mide:
  · fotos buenas de Allie contra la referencia → tiene que decir «es ella»
  · la desconocida contra la referencia        → tiene que decir «NO es ella»
  · y que haya un hueco claro entre unas y otra, no un empate por los pelos

Necesita descargar dos modelos de OpenCV (37 MB en total) la primera vez.
Desde la sesión de Claude no se alcanza raw.githubusercontent, así que esto
se ejecuta en Actions y deja el resultado escrito en cara/informe.md.
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import cara  # noqa: E402

REFERENCIA = BASE / "videos" / "prueba" / "0-REFERENCIA.jpg"

# Caras que SÍ son Allie. Se cogen del banco las más recientes que existan.
DESCONOCIDA = BASE / "videos" / "prueba" / "sana-sin-referencia.jpg"

INFORME = BASE / "cara" / "informe.md"


def buenas(cuantas=12):
    """Fotos de Allie de tandas DISTINTAS, no doce de la misma tarde.

    Una tanda comparte ropa, sitio y luz, así que doce fotos de una sola
    tanda miden una situación, no el rango real. Se coge una por tanda,
    empezando por las más recientes, y se añaden las de videos/prueba, que
    son de otros días y otros generadores.
    """
    vistas, fotos = set(), []
    for f in sorted((BASE / "banco" / "fotos").glob("*.jpg"), reverse=True):
        tanda = f.name.rsplit("-", 1)[0]
        if tanda in vistas:
            continue
        vistas.add(tanda)
        fotos.append(f)
        if len(fotos) >= cuantas:
            break
    for n in ("foto-20261008-1408-1.jpg", "foto-20261008-1408-2.jpg",
              "foto-20261007-2155.jpg", "sana-con-foto-de-referencia.jpg"):
        otra = BASE / "videos" / "prueba" / n
        if otra.exists():
            fotos.append(otra)
    return fotos


def main():
    lineas, fallos = ["# Comprobación de cara (OpenCV, sin API)", ""], []
    INFORME.parent.mkdir(exist_ok=True)

    def guardar():
        INFORME.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    def comprobar(que, bien, detalle=""):
        lineas.append(f"- {'✅' if bien else '❌'} {que}" + (f" · {detalle}" if detalle else ""))
        print(("ok   " if bien else "MAL  ") + que + (f"  ·  {detalle}" if detalle else ""),
              flush=True)
        if not bien:
            fallos.append(que)

    if not REFERENCIA.exists():
        lineas.append(f"No está la referencia en {REFERENCIA}")
        guardar()
        sys.exit(1)

    try:
        disponible = cara.hay()
    except Exception:  # noqa: BLE001
        disponible = False
    if not disponible:
        lineas += ["**No se pudieron cargar los modelos.**", "", "```",
                   traceback.format_exc()[-1500:], "```"]
        guardar()
        print("\n".join(lineas), flush=True)
        sys.exit(1)
    lineas += [f"Umbral: **{cara.UMBRAL}**", ""]

    ref = REFERENCIA.read_bytes()

    lineas += ["## Fotos de Allie (deben pasar)", ""]
    parecidos_buenos = []
    for f in buenas():
        try:
            ok, p, motivo = cara.misma_persona(ref, f.read_bytes())
        except Exception as e:  # noqa: BLE001
            comprobar(f"{f.name}", False, f"reventó: {type(e).__name__}: {e}")
            continue
        parecidos_buenos.append(p)
        comprobar(f"{f.name}", ok, f"parecido {p:.3f}")

    lineas += ["", "## La desconocida (debe fallar)", ""]
    parecido_malo = None
    if DESCONOCIDA.exists():
        ok, parecido_malo, motivo = cara.misma_persona(ref, DESCONOCIDA.read_bytes())
        comprobar("la mujer que se publicó por error NO pasa", not ok,
                  f"parecido {parecido_malo:.3f}")
    else:
        comprobar("existe la foto de la desconocida", False, str(DESCONOCIDA))

    # Lo que de verdad importa no es acertar por los pelos, sino que haya
    # sitio entre las dos nubes: si el peor acierto y el fallo están pegados,
    # cualquier foto rara del futuro cae del lado malo.
    if parecidos_buenos and parecido_malo is not None:
        hueco = min(parecidos_buenos) - parecido_malo
        lineas += ["", f"**Hueco**: la peor foto buena saca {min(parecidos_buenos):.3f} "
                       f"y la desconocida {parecido_malo:.3f} · diferencia {hueco:.3f}", ""]
        comprobar("hay un margen claro entre Allie y la desconocida", hueco > 0.15,
                  f"diferencia {hueco:.3f}")

    lineas += ["", f"**{len(fallos)} fallos.**", ""]
    guardar()
    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal", flush=True)
        sys.exit(1)
    print("\nla cara se comprueba bien sin gastar cuota", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        INFORME.parent.mkdir(exist_ok=True)
        INFORME.write_text("# Comprobación de cara\n\nReventó:\n\n```\n"
                           + traceback.format_exc()[-2500:] + "\n```\n", encoding="utf-8")
        raise
