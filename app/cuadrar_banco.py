"""Devuelve al banco las fotos que se marcaron usadas y nunca se publicaron.

EL AGUJERO. banco.coger() marca las fotos como usadas ANTES de publicar, y
quien las coge las devuelve si algo falla. Eso cubre el caso normal. No
cubre dos:

  1. Que el proceso muera de golpe —tiempo agotado, trabajo cancelado— y no
     llegue a ejecutarse el `devolver`.
  2. Que alguien commitee banco/indice.json a mitad de un montaje, con las
     fotos marcadas y antes de que se devuelvan. Eso lo hice yo el 22 de
     octubre con tres `git add -A` seguidos mientras probaba el reel de
     lista, y dejó siete fotos de cafetería marcadas como gastadas sin
     haberse publicado jamás. Al día siguiente el reel de librerías no pudo
     montarse porque no quedaba ninguna.

AL MIRARLO APARECIÓ ALGO PEOR: treinta fotos marcadas como usadas que no
salen en ninguna publicación, desde el 10 de octubre. Treinta fotos
generadas y pagadas que nadie ha visto.

POR QUÉ NO SE LIBERAN LAS TREINTA. Porque no se puede demostrar que no se
publicaran. Un carrusel registra en videos/publicados.json los nombres de
sus jpg, así que de esos se sabe. Un REEL registra solo el mp4: las fotos
que lo compusieron no quedan anotadas en ninguna parte —videos/del-banco.json
guarda únicamente la última tanda cogida y se sobrescribe en cada ejecución.
Liberar a ciegas significaría republicar fotos que la gente ya ha visto.

ASÍ QUE ESTE PROGRAMA ES CONSERVADOR. Solo devuelve una tanda cuando se
puede demostrar que no se publicó, y para eso hace falta que la publicación
de reels empiece a anotar sus fotos: eso es lo que hace ahora publicar.py.
De aquí a unas semanas, cuando todas las publicaciones vivas lleven su
anotación, esto podrá liberar sin riesgo. Mientras tanto pide confirmación
por nombre de tanda y no adivina nada.

    python app/cuadrar_banco.py                 → solo informa
    python app/cuadrar_banco.py 20261020-184414 → devuelve esa tanda
"""
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
INDICE = BASE / "banco" / "indice.json"
PUBLICADOS = BASE / "videos" / "publicados.json"


def leer(p, por_omision):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return por_omision


def fotos(d):
    return d if isinstance(d, list) else d.get("fotos", [])


def publicadas():
    """Los nombres de foto que constan en alguna publicación.

    Incluye `fotos` además de `archivos`, que es lo que anota publicar.py
    desde el 22 de octubre para los reels.
    """
    nombres = set()
    for p in leer(PUBLICADOS, []):
        for a in (p.get("archivos") or []):
            nombres.add(a)
        for a in (p.get("fotos") or []):
            nombres.add(a)
        if p.get("archivo") and p["archivo"].endswith(".jpg"):
            nombres.add(p["archivo"])
    return nombres


def huerfanas(d):
    """Marcadas como usadas y sin rastro en ninguna publicación."""
    vistas = publicadas()
    return [x for x in fotos(d)
            if x.get("usada") and not x.get("retirada")
            and x["archivo"] not in vistas]


def main():
    d = leer(INDICE, {})
    sueltas = huerfanas(d)
    por_tanda = Counter(x.get("tanda") for x in sueltas)

    print(f"{len(sueltas)} fotos marcadas como usadas sin aparecer en ninguna "
          f"publicación, en {len(por_tanda)} tandas:", flush=True)
    for t, n in sorted(por_tanda.items()):
        print(f"   {t}  ·  {n} fotos", flush=True)

    pedidas = [a for a in sys.argv[1:] if a.strip()]
    if not pedidas:
        print("\nNo devuelvo nada. Un reel no anota qué fotos usó, así que una "
              "tanda sin rastro puede estar publicada dentro de un vídeo.",
              flush=True)
        print("Para devolver una, pásala por su nombre:", flush=True)
        print(f"   python app/cuadrar_banco.py {next(iter(por_tanda), 'TANDA')}",
              flush=True)
        return

    tocadas = 0
    for x in fotos(d):
        if x.get("tanda") in pedidas and x.get("usada") and not x.get("retirada"):
            if x["archivo"] in publicadas():
                print(f"   NO devuelvo {x['archivo']}: consta publicada", flush=True)
                continue
            x["usada"] = False
            tocadas += 1
    INDICE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    libres = sum(1 for x in fotos(d) if not x.get("usada") and not x.get("retirada"))
    print(f"\n{tocadas} fotos devueltas al banco. Ahora hay {libres} libres.",
          flush=True)


if __name__ == "__main__":
    main()
