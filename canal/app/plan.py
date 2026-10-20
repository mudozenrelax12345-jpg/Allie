"""Escribe el plan visual en texto, para poder revisarlo antes de montar.

Es la pieza que faltaba. Montar un vídeo cuesta cuarenta minutos; leer esta
lista cuesta dos. Aquí se ve, frase a frase, qué se oye y qué se ve al mismo
tiempo — que es justo lo que no se podía comprobar mirando la lista de planos
después, cuando ya estaba todo hecho.

  video/plan.txt

No necesita que exista el material: trabaja solo con el guion, las marcas de
tiempo y el plan. Se puede lanzar en segundos.
"""
import json
import math
import sys
from pathlib import Path

import yaml

import config
import ritmo
import tarjetas

BASE = Path(__file__).resolve().parent.parent
AUDIO = BASE / "audio"
SALIDA = BASE / "video" / "plan.txt"

MINIMO_IMAGEN = 2.4
TOPE_RACHA = 25.0      # segundos seguidos de texto sin una imagen en medio
SEGUNDOS_POR_ELEMENTO = 8.0   # lo que puede durar un párrafo por cada cosa distinta

# Estas pantallas llevan texto pero no son un muro de texto: una rejilla que
# se enciende, unas barras que crecen, una línea de tiempo que se traza o un
# documento subrayándose cambian solos y rompen la monotonía igual que una
# imagen. No cuentan para la racha.
DEMUESTRAN = {"rejilla", "barras", "cronologia", "subrayado"}


def clase(nombre, fichas):
    if nombre in fichas:
        return "tarjeta"
    if str(nombre).startswith("DOC"):
        return "documento"
    if str(nombre).startswith("g-"):
        return "imagen"
    return "clip"




def reloj(s):
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def main():
    marcas = json.loads((AUDIO / "marcas.json").read_text(encoding="utf-8"))
    monta = yaml.safe_load(config.ruta("montaje.yml").read_text(encoding="utf-8"))
    tarj = yaml.safe_load(config.ruta("tarjetas.yml").read_text(encoding="utf-8"))
    fichas = {t["nombre"]: t for t in tarj.get("tarjetas", [])}
    duraciones = {n: tarjetas.leible(t) for n, t in fichas.items()}
    plan = monta.get("plan") or {}
    rotulos = monta.get("rotulos") or {}

    filas, cuenta = [], {"tarjeta": 0, "documento": 0, "imagen": 0, "clip": 0}
    cortas, caidos, flacos = [], [], []
    racha, peor = [], []
    t = 0.0
    for p in marcas["planos"]:
        pedidos = (plan.get(p["acto"]) or {}).get(p["parrafo"]) or []
        dur = max(p["duracion"], 0.5)
        pedidos = ritmo.ordenar(pedidos, p.get("texto", ""),
                                lambda x: ritmo.texto_ficha(fichas.get(x)),
                                p.get("frases"), p.get("inicio"), dur)
        minimos = {x: ritmo.minimo_de(x, clase(x, fichas), duraciones, MINIMO_IMAGEN)
                   for x in pedidos}
        fracs = {x: ritmo.donde(ritmo.texto_ficha(fichas.get(x)), p.get("texto", ""),
                                p.get("frases"), p.get("inicio"), dur)
                 for x in pedidos}
        trozos = (ritmo.repartir(pedidos, dur, minimos, fracs,
                                 lambda x: clase(x, fichas) == "tarjeta")
                  if pedidos else [("— NADA —", dur)])
        eti = (rotulos.get(p["acto"]) or {}).get(p["parrafo"])

        filas.append("")
        filas.append(f"{reloj(t)}  ── {p['acto']}.{p['parrafo']} "
                     f"({dur:.1f}s) ─────────────────────────────")
        filas.append(f"       SE OYE:  {p.get('texto', '')}")
        for i, (nombre, d) in enumerate(trozos):
            c = clase(nombre, fichas)
            cuenta[c] = cuenta.get(c, 0) + 1
            marca = f"   ◀ rótulo: {eti}" if eti and i == 0 and c in ("imagen", "clip") else ""
            if c == "tarjeta" and d < minimos.get(nombre, 0) - 0.05:
                marca += f"   ⚠ NO SE PUEDE LEER (necesita {minimos[nombre]:.1f}s)"
                cortas.append(f"{p['acto']}.{p['parrafo']} {nombre}")
            filas.append(f"       SE VE:   [{c:>9}] {nombre}  ({d:.1f}s){marca}")
            formato = (fichas.get(nombre) or {}).get("formato", "")
            if c in ("tarjeta", "documento") and formato not in DEMUESTRAN:
                racha.append((f"{p['acto']}.{p['parrafo']}", nombre, d))
            else:
                if sum(x[2] for x in racha) > sum(x[2] for x in peor):
                    peor = racha[:]
                racha = []
            if c == "tarjeta":
                f = fichas[nombre]
                texto = f.get("lineas") or f.get("texto") or f.get("numero") or f.get("titulo")
                if isinstance(texto, list):
                    texto = " / ".join(texto)
                if f.get("filas"):
                    texto = " · ".join(f"{x['de']}: {x['a']}" for x in f["filas"])
                filas.append(f"                    «{texto}»")
        fuera = [x for x in pedidos if x not in {n for n, _ in trozos}]
        for x in fuera:
            filas.append(f"       ✗ no cabe:  {x}")
            caidos.append(f"{p['acto']}.{p['parrafo']} {x}")

        # ¿Tiene este párrafo cosas distintas que enseñar para lo que dura?
        distintos = len({n for n, _ in trozos if n != "— NADA —"})
        quiere = max(1, math.ceil(dur / SEGUNDOS_POR_ELEMENTO))
        if distintos < quiere:
            flacos.append((f"{p['acto']}.{p['parrafo']}", dur, distintos, quiere,
                           sorted({n for n, _ in trozos})))
        t += dur

    # Nada de montar con el plan pidiendo cosas que no existen.
    material = yaml.safe_load(config.ruta("material.yml").read_text(encoding="utf-8"))
    hay = ({c["nombre"] for c in material.get("clips") or []}
           | {i["nombre"] for i in material.get("imagenes") or []}
           | set(fichas) | {"DOC-A", "DOC-B"})
    pedidos = {x for a in plan.values() for it in a.values() for x in it}
    huerfanos = sorted(pedidos - hay)
    if huerfanos:
        print("✗ el plan pide material que no existe:", ", ".join(huerfanos))
        sys.exit(1)

    # Nada de montar con medio minuto seguido de pantallas de texto.
    #
    # En el vídeo 2 hubo cincuenta y seis segundos sin una sola imagen: nueve
    # tarjetas encadenadas. El ritmo de corte estaba bien y aun así se hacía
    # pesado, porque una tarjeta se anima segundo y medio y luego se queda
    # quieta. Esto no depende de que yo me acuerde de mirarlo.
    if sum(x[2] for x in racha) > sum(x[2] for x in peor):
        peor = racha[:]
    largo = sum(x[2] for x in peor)
    if largo > TOPE_RACHA:
        print(f"✗ {largo:.0f}s seguidos de texto sin una sola imagen "
              f"({len(peor)} tarjetas), desde el párrafo {peor[0][0]}:")
        print("    " + ", ".join(x[1] for x in peor))
        print(f"  Mete una imagen en medio. El tope son {TOPE_RACHA:.0f}s.")
        sys.exit(1)

    # Nada de montar con un párrafo largo que solo tiene una cosa que enseñar.
    #
    # Esto es lo que de verdad hacía aburrido el vídeo 3, y no se veía en
    # ningún sitio. Once párrafos llevaban un solo elemento para diez o
    # diecisiete segundos. Lo que sobra tiene que quedarse en alguna pantalla,
    # así que salieron ocho tarjetas congeladas de hasta diecisiete segundos y
    # trece pares de planos seguidos con la misma foto. El montaje no puede
    # arreglarlo: con una sola cosa que enseñar, no hay nada que cortar.
    #
    # Se mide en cosas distintas, no en planos, porque partir una imagen en
    # dos trozos no da material nuevo: da la misma foto dos veces.
    if flacos:
        print(f"✗ {len(flacos)} párrafos no tienen material para lo que duran "
              f"(uno distinto por cada {SEGUNDOS_POR_ELEMENTO:.0f}s como mucho):")
        for clave, dur, hay_, quiere, cuales in flacos:
            print(f"    {clave}  {dur:.1f}s  tiene {hay_}, necesita {quiere}"
                  f"   [{', '.join(cuales)}]")
        print("  Añade imágenes a ese párrafo en montaje.yml.")
        sys.exit(1)

    total = sum(cuenta.values())
    cabecera = [
        "PLAN VISUAL · " + config.cual(),
        "=" * 72,
        "Lo que se oye y lo que se ve, frase a frase.",
        "",
        f"{total} planos · {marcas['total']/60:.1f} min",
        "  tarjetas de texto: %d (%d%%)" % (cuenta['tarjeta'], 100*cuenta['tarjeta']//total),
        "  documentos:        %d" % cuenta["documento"],
        "  imágenes:          %d" % cuenta["imagen"],
        "  clips de archivo:  %d" % cuenta["clip"],
        "  INFORMACIÓN EN PANTALLA: %d%%" % (100*(cuenta['tarjeta']+cuenta['documento'])//total),
    ]
    if cortas:
        cabecera += ["", "⚠ %d tarjetas no se pueden leer en el tiempo que tienen:" % len(cortas),
                     "    " + ", ".join(cortas)]
    if caidos:
        cabecera += ["", "✗ %d cosas no caben y no se verán:" % len(caidos),
                     "    " + ", ".join(caidos)]
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text("\n".join(cabecera + filas) + "\n", encoding="utf-8")
    print("\n".join(cabecera))
    print(f"\n· plan escrito en {SALIDA}")


if __name__ == "__main__":
    main()
