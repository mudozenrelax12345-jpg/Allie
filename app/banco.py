"""Guarda en el repositorio las fotos de Allie que ya están publicadas en su perfil.

Las dos formas gratuitas de generar fotos nuevas conservando su cara se
cerraron la misma semana. Pero fotos de Allie hay: las que ya están en su
cuenta. Son suyas, tienen su cara y están aprobadas, que es justo lo que no da
ningún generador ahora mismo.

De aquí salen los reels mientras no haya un generador. Y si algún día llegan
fotos nuevas —hechas a mano en la app de Gemini, por ejemplo— basta con
dejarlas en videos/banco/ y entran en el mismo saco sin tocar nada.
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import main as cuenta  # noqa: E402
from ig import IG  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
BANCO = BASE / "videos" / "banco"
FICHA = BANCO / "indice.json"

MINIMO = 60_000      # por debajo de esto no es una foto, es una miniatura


def log(m):
    print(f"· {m}", flush=True)


def traer():
    token, ig_id, page_id = cuenta.credenciales()
    api = IG(token, ig_id, page_id)
    quien = api.cuenta()
    log(f"Cuenta: @{quien.get('username')} · {quien.get('media_count')} publicaciones")

    # Las publicaciones, con la dirección de la imagen. Un carrusel no trae
    # imagen propia: hay que entrar a ver sus hijas.
    medios = api._lista(f"{api.yo}/media", 200, limit=25,
                        fields="id,media_type,media_url,thumbnail_url,permalink,timestamp,caption")

    BANCO.mkdir(parents=True, exist_ok=True)
    indice = json.loads(FICHA.read_text(encoding="utf-8")) if FICHA.exists() else {}
    nuevas = 0

    for m in medios:
        piezas = []
        if m.get("media_type") == "CAROUSEL_ALBUM":
            try:
                hijas = api._req("GET", m["id"], fields="children{id,media_type,media_url}")
                for h in (hijas.get("children") or {}).get("data", []):
                    if h.get("media_type") == "IMAGE" and h.get("media_url"):
                        piezas.append((h["id"], h["media_url"]))
            except Exception as e:  # noqa: BLE001
                log(f"No pude abrir el carrusel {m['id']}: {e}")
        elif m.get("media_type") == "IMAGE" and m.get("media_url"):
            piezas.append((m["id"], m["media_url"]))

        for pid, url in piezas:
            destino = BANCO / f"{pid}.jpg"
            if destino.exists():
                continue
            try:
                r = requests.get(url, timeout=120)
                r.raise_for_status()
            except requests.RequestException as e:
                log(f"No pude bajar {pid}: {type(e).__name__}")
                continue
            if len(r.content) < MINIMO:
                log(f"{pid}: solo {len(r.content)//1024} KB, la descarto")
                continue
            destino.write_bytes(r.content)
            indice[destino.name] = {"publicada": m.get("timestamp"),
                                    "enlace": m.get("permalink"), "veces_usada": 0}
            nuevas += 1
            log(f"Guardada {destino.name} ({len(r.content)//1024} KB)")

    # Las que alguien haya dejado a mano en la carpeta también cuentan.
    for suelta in sorted(BANCO.glob("*.jpg")):
        indice.setdefault(suelta.name, {"publicada": None, "enlace": None, "veces_usada": 0})

    FICHA.write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"{nuevas} fotos nuevas · {len(indice)} en el banco")
    return len(indice)


if __name__ == "__main__":
    try:
        total = traer()
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"\n✗ No se pudo llenar el banco: {e}")
        sys.exit(1)
    if total < 4:
        print(f"\n✗ Solo hay {total} fotos. Para un reel hacen falta 4.")
        sys.exit(1)
