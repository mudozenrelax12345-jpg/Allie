"""Prepara varias publicaciones de golpe, cada una con sus fotos verificadas.

La tarea de los lunes construía ella misma las direcciones de Pollinations y
se las pasaba a Metricool. Eso dejó de funcionar sin avisar: el modelo que
copiaba la cara pasó a ser de pago, y el que queda gratis devuelve a otra
mujer. Nadie lo vio hasta que la cuenta llevaba una semana publicando a una
desconocida.

Aquí las fotos se generan con el mismo camino que ya está probado —FLUX.1
Kontext desde la foto de Allie—, cada una pasa por el revisor, y la dirección
pública se comprueba abriéndola antes de darla por buena. Lo que no pasa los
tres filtros no sale.

Deja videos/semana.json con las publicaciones listas para programar.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foto  # noqa: E402
import reel  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "videos" / "semana.json"
FOTOS = BASE / "videos" / "semana"

POR_PUBLICACION = int(os.environ.get("FOTOS_POR_POST", "3"))


def log(m):
    print(f"· {m}", flush=True)


def main():
    temas = [t.strip() for t in os.environ.get("TEMAS", "").split("|") if t.strip()]
    p = reel.persona()
    if not temas:
        temas = (p.get("temas_reel") or ["un día en Madrid"])[:4]
    log(f"{len(temas)} publicaciones: {', '.join(temas)}")

    FOTOS.mkdir(parents=True, exist_ok=True)
    for viejo in FOTOS.glob("*.jpg"):
        viejo.unlink()

    publicaciones = []
    for n, tema in enumerate(temas, 1):
        log(f"\n── publicación {n}/{len(temas)} · {tema}")
        os.environ["TEMA"] = tema
        try:
            g = foto.idea(p, POR_PUBLICACION)
        except Exception as e:  # noqa: BLE001
            log(f"No se pudo pensar la publicación {n}: {e}")
            continue

        descartes, enlaces, fallos = [], [], []
        for i, escena in enumerate(g["escenas"], 1):
            datos = foto.una_foto(escena, p, f"{n}.{i}", descartes)
            if datos is None:
                continue
            f = FOTOS / f"p{n}-foto{i}.jpg"
            f.write_bytes(datos)
            try:
                enlaces.append(reel.subir(f, fallos))
            except Exception as e:  # noqa: BLE001
                fallos.append(f"{f.name}: {e}")

        if not enlaces:
            log(f"Publicación {n} sin fotos aprovechables; se salta")
            continue
        publicaciones.append({
            "tema": tema, "idea": g.get("idea", ""), "texto": g.get("texto", ""),
            "hashtags": " ".join(h if str(h).startswith("#") else f"#{h}"
                                 for h in g.get("hashtags", [])),
            "media": enlaces, "descartadas": descartes, "fallos_subida": fallos,
        })
        log(f"Publicación {n} lista con {len(enlaces)} fotos")

    SALIDA.write_text(json.dumps({
        "creado": datetime.now(timezone.utc).isoformat(),
        "publicaciones": publicaciones,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"\n{len(publicaciones)} de {len(temas)} publicaciones listas en {SALIDA.name}")
    if not publicaciones:
        raise RuntimeError("Ninguna publicación salió adelante.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · semana\n\n{detalle}\n",
            encoding="utf-8")
        sys.exit(1)
