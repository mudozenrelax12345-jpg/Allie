"""Sube a un alojamiento público fotos concretas del banco y apunta su dirección.

Para qué. Metricool solo acepta imágenes por dirección pública, y los repos son
privados, así que una foto del banco no se puede programar tal cual. Esto coge
las fotos que se le digan por nombre, las sube con el subidor de reel.py —que
además comprueba que al otro lado hay de verdad una imagen, porque un sitio que
devuelve la página en vez del fichero hace que Metricool conteste «failed to
normalize media»— y deja las direcciones en banco/subidas.json.

Por qué por nombre y no «dame tres de casa»: las fotos se miran una por una
antes de publicar, y lo que se sube tiene que ser exactamente lo que se miró.

Las fotos subidas se marcan como usadas en el índice, para que no vuelvan a
salir en otra publicación. Si alguna no se pudo subir, no se marca ninguna y el
trabajo falla: media publicación es peor que ninguna.

Entrada:  FOTOS=20261010-1130-1.jpg,20261010-1130-2.jpg,...
Deja:     banco/subidas.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ajustes  # noqa: E402
import banco  # noqa: E402
import reel  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "banco" / "subidas.json"

NOMBRES = [x.strip() for x in ajustes.texto("FOTOS").split(",") if x.strip()]


def log(m):
    print(f"· {m}", flush=True)


def main():
    if not NOMBRES:
        raise SystemExit("Hace falta FOTOS con los nombres separados por comas")

    rutas = []
    for n in NOMBRES:
        r = banco.FOTOS / Path(n).name
        if not r.exists():
            raise SystemExit(f"No existe en el banco: {r.name}")
        rutas.append(r)

    enlaces, dichos = [], []
    for r in rutas:
        log(f"Subiendo {r.name}…")
        enlaces.append(reel.subir(r, dichos))

    # Solo se marcan como usadas si TODAS subieron: reel.subir() revienta si
    # ninguna de las cinco casas acepta el fichero, y entonces no llegamos aquí
    # con el índice tocado.
    indice = banco.leer()
    cuando = datetime.now(timezone.utc).isoformat()
    marcadas = 0
    quiero = {r.name for r in rutas}
    for f in indice["fotos"]:
        if f["archivo"] in quiero:
            f["usada"] = cuando
            marcadas += 1
    banco.guardar(indice)

    SALIDA.write_text(json.dumps({
        "cuando": cuando,
        "fotos": [r.name for r in rutas],
        "enlaces": enlaces,
        "dichos": dichos,
        "marcadas": marcadas,
        "libres": len(banco.disponibles(indice)),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    log(f"\n{len(enlaces)} fotos subidas · {marcadas} marcadas como usadas")
    for e in enlaces:
        print(f"ENLACE: {e}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · subir-banco\n\n"
            f"{detalle}\n", encoding="utf-8")
        sys.exit(1)
