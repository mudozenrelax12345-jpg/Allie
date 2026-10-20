"""Publica UN Short al día: el siguiente que no se haya publicado.

POR QUÉ UNO AL DÍA Y NO LOS DIEZ DE GOLPE. Un canal que suelta diez vídeos
una tarde y luego nada parece una granja de contenido, y los diez compiten
entre sí por el mismo hueco en el feed. Lo que mueve la aguja en Shorts es
la constancia: por debajo de tres a la semana el alcance se encoge, y por
encima de siete la retención de cada uno baja. Cinco es la banda buena.

QUÉ DÍAS. Con los datos de 6.175 publicaciones delante: sábado 1,13 ·
domingo 1,12 · lunes 1,02 · viernes 1,00 · martes 0,97 · jueves 0,96 ·
miércoles 0,89. Así que se publica lunes, martes, viernes, sábado y
domingo, que son cinco e incluyen los tres mejores. Miércoles y jueves,
los dos peores, se descansan.

A QUÉ HORA, Y ESTA ES LA PARTE QUE SE OLVIDA. El canal está en inglés y
habla de empresas americanas: la audiencia no está en Madrid. La hora que
importa es la de Nueva York, donde el pico está a la una de la tarde
(1,28 veces lo normal). Publicar a las diez de la mañana de Madrid sería
las cuatro de la madrugada allí.

Dicho esto, la hora es un factor MENOR en Shorts: el feed sigue probando
el vídeo días después de subirlo. Primero la constancia, luego la hora.

SE MONTA EN EL MOMENTO, no se guarda. Montar un Short cuesta tres o cuatro
minutos de máquina y son gratis; guardar diez mp4 en el repositorio son
36 MB que no pintan nada ahí.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corto  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
REGISTRO = BASE / "estado" / "cortos-publicados.json"


def log(m):
    print(f"· {m}", flush=True)


def publicados():
    if not REGISTRO.exists():
        return []
    try:
        return json.loads(REGISTRO.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def siguiente():
    """El primero de la lista que no se haya publicado. None si no queda."""
    ya = {p.get("id") for p in publicados()}
    for c in corto.cargar():
        if c["id"] not in ya:
            return c
    return None


def anotar(corto_id, estado):
    ya = publicados()
    ya.append({"id": corto_id, "cuando": datetime.now(timezone.utc).isoformat(),
               **(estado or {})})
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text(json.dumps(ya, ensure_ascii=False, indent=1), encoding="utf-8")


def correr(programa, entorno):
    r = subprocess.run([sys.executable, str(Path(__file__).parent / programa)],
                       env={**os.environ, **entorno}, cwd=str(BASE))
    if r.returncode:
        raise RuntimeError(f"{programa} falló con código {r.returncode}")


def main():
    seco = (os.environ.get("EN_SECO") or "").strip().lower() in ("si", "sí", "true", "1")

    # Sin las llaves de YouTube no hay nada que hacer, y NO es un fallo: es
    # que todavía no se han puesto. Si esto reventara, el cron dejaría un
    # aspa roja todos los días y acabaríamos sin mirar ninguna, que es
    # exactamente como se pierde el aspa que sí importaba.
    faltan = [n for n in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
              if not (os.environ.get(n) or "").strip()]
    if faltan and not seco:
        log("Todavía no están las llaves de YouTube: " + ", ".join(faltan))
        log("Se montará y publicará solo en cuanto estén. No hago nada más.")
        return

    c = siguiente()
    if not c:
        # No es un fallo. Es que se acabó el material, que es una noticia
        # distinta y hay que verla venir con tiempo.
        log("NO QUEDAN SHORTS SIN PUBLICAR.")
        log("Los diez salieron de tres guiones largos. Para seguir publicando "
            "hacen falta guiones nuevos: o un vídeo largo más, que da tres o "
            "cuatro, o Shorts escritos directamente.")
        (BASE / "estado").mkdir(parents=True, exist_ok=True)
        (BASE / "estado" / "SE-ACABARON-LOS-CORTOS.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n\n"
            "Se han publicado los diez Shorts. Hacen falta guiones nuevos en "
            "cortos/cortos.yml.\n", encoding="utf-8")
        return

    quedan = len(corto.cargar()) - len(publicados()) - 1
    log(f"Toca «{c['id']}» · {c['titulo']}")
    log(f"Después de este quedan {quedan}")
    if quedan <= 2:
        log("AVISO: quedan dos o menos. Hay que escribir más.")

    correr("corto.py", {"CORTO": c["id"]})

    mp4 = corto.SALIDA / f"{c['id']}.mp4"
    ficha = corto.SALIDA / f"{c['id']}.yml"
    if not mp4.exists():
        raise RuntimeError(f"El montaje dijo que sí pero no está {mp4}")
    log(f"Montado · {mp4.stat().st_size / 1e6:.1f} MB")

    if seco:
        log("EN_SECO: montado pero no se sube, y no se anota como publicado.")
        return

    correr("subir.py", {"MP4": str(mp4), "FICHA": str(ficha),
                        "PRIVACIDAD": os.environ.get("PRIVACIDAD") or "public"})

    # Lo que subir.py averiguó preguntándole a YouTube.
    estado = {}
    subidos = BASE / "estado" / "subidos.json"
    if subidos.exists():
        try:
            estado = (json.loads(subidos.read_text(encoding="utf-8")) or [{}])[-1]
        except Exception:  # noqa: BLE001
            pass
    anotar(c["id"], {k: estado.get(k) for k in ("enlace", "privacidad", "subida")})
    log(f"PUBLICADO · {estado.get('enlace', 'sin enlace')}")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "estado").mkdir(parents=True, exist_ok=True)
        (BASE / "estado" / "ULTIMO-FALLO-CORTO-DIARIO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n\n{detalle}\n",
            encoding="utf-8")
        raise
