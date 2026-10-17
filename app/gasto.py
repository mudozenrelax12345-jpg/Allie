"""Resume en qué se va el cupo de Cloudflare, por día y por trabajo.

Lee las líneas que deja cloudflare._apuntar y escribe una tabla legible. La
pregunta que tiene que contestar es la que el 17 de octubre no se pudo
contestar: «el cupo estaba agotado a las cuatro de la mañana, ¿quién se lo
había comido?».
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LINEAS = BASE / "estado" / "gasto-cloudflare.jsonl"
RESUMEN = BASE / "estado" / "gasto-cloudflare.md"

TECHO = 10000      # las neuronas que regala Cloudflare al día


def leer():
    if not LINEAS.exists():
        return []
    salida = []
    for linea in LINEAS.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            salida.append(json.loads(linea))
        except Exception:  # noqa: BLE001
            continue
    return salida


def main():
    apuntes = leer()
    if not apuntes:
        print("· todavía no hay apuntes de gasto", flush=True)
        return

    por_dia = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))  # quien -> [n, ok, fallos]
    for a in apuntes:
        dia = str(a.get("cuando", ""))[:10]
        fila = por_dia[dia][a.get("quien", "?")]
        fila[0] += int(a.get("neuronas") or 0)
        fila[1] += 1 if a.get("ok") else 0
        fila[2] += 0 if a.get("ok") else 1

    texto = ["# En qué se va el cupo de Cloudflare", "",
             f"Diez mil neuronas al día. Estimaciones nuestras por modelo, no "
             f"cifras oficiales: valen para comparar, no para facturar.", ""]
    for dia in sorted(por_dia, reverse=True):
        total = sum(v[0] for v in por_dia[dia].values())
        texto += [f"## {dia} · {total} neuronas "
                  f"({round(100 * total / TECHO)} % del día)", "",
                  "| trabajo | neuronas | llamadas bien | llamadas mal |",
                  "|---|---|---|---|"]
        for quien, (n, ok, mal) in sorted(
                por_dia[dia].items(), key=lambda kv: -kv[1][0]):
            texto.append(f"| {quien} | {n} | {ok} | {mal} |")
        texto.append("")

    RESUMEN.write_text("\n".join(texto) + "\n", encoding="utf-8")
    print("\n".join(texto[:14]), flush=True)


if __name__ == "__main__":
    sys.exit(main())
