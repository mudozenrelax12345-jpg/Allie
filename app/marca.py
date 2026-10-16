"""Marcar el vídeo como generado por IA dentro del propio fichero.

POR QUÉ. La declaración que va en el pie la leen las personas. Esto es la
otra mitad: que lo lean las máquinas. El artículo 50.2 del reglamento
europeo de IA pide que el contenido sintético lleve un marcado legible por
máquina; esa obligación recae sobre el proveedor del generador y no sobre
Teresa, pero el marcado es gratis, y además es lo que hace que plataformas
como Instagram pongan su propia etiqueta de «Información de IA» sin que
nadie se lo pida.

QUÉ SE ESCRIBE. El valor estándar del IPTC para esto:

    DigitalSourceType = trainedAlgorithmicMedia
    http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia

que significa exactamente «creado íntegramente por un modelo entrenado».
Es el mismo término que usan Adobe, Google y Meta para detectar contenido
generado, así que no es una invención nuestra.

QUÉ NO ES. Esto NO es una credencial C2PA firmada criptográficamente. Una
C2PA de verdad necesita un certificado y una cadena de firma que aquí no
tenemos. Es un marcado honesto y legible, no una prueba infalsificable, y
conviene no venderlo como lo que no es.

CÓMO. Con ffmpeg, copiando los flujos sin recodificar: el vídeo no se toca,
solo se le añaden las etiquetas. Tarda menos de un segundo y no pierde
calidad.
"""
import shutil
import subprocess
import sys
from pathlib import Path

IPTC = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
AVISO = ("Contenido generado con inteligencia artificial. Allie es un personaje "
         "de ficción creado con IA; no es una persona real.")

ETIQUETAS = {
    "comment": AVISO,
    "description": AVISO,
    "DigitalSourceType": IPTC,
    "GenAI": "true",
    "copyright": "Allie (personaje de ficción generado con IA)",
}


def marcar(ruta):
    """Devuelve (ok, detalle). Si falla, el vídeo se queda como estaba."""
    ruta = Path(ruta)
    if not ruta.exists():
        return False, f"no existe {ruta}"
    salida = ruta.with_suffix(".marcado.mp4")
    orden = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(ruta),
             "-map", "0", "-c", "copy", "-movflags", "use_metadata_tags"]
    for k, v in ETIQUETAS.items():
        orden += ["-metadata", f"{k}={v}"]
    orden.append(str(salida))
    try:
        r = subprocess.run(orden, capture_output=True, text=True, timeout=180)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    if r.returncode != 0 or not salida.exists() or salida.stat().st_size < 1000:
        salida.unlink(missing_ok=True)
        return False, (r.stderr or "ffmpeg falló").strip()[:300]
    # Solo se sustituye si el resultado es creíble: un vídeo que se queda a
    # medias por marcarlo sería cambiar una formalidad por un fallo real.
    if salida.stat().st_size < ruta.stat().st_size * 0.8:
        salida.unlink(missing_ok=True)
        return False, "el vídeo marcado salió demasiado pequeño; lo dejo como estaba"
    shutil.move(str(salida), str(ruta))
    return True, "marcado como generado con IA"


def leer(ruta):
    """Las etiquetas que tiene el fichero, para poder comprobarlo."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format_tags",
             "-of", "default=noprint_wrappers=1", str(ruta)],
            capture_output=True, text=True, timeout=60)
        return r.stdout
    except Exception as e:  # noqa: BLE001
        return f"(no se pudo leer: {e})"


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        ok, detalle = marcar(arg)
        print(f"{'ok  ' if ok else 'MAL '} {arg}: {detalle}", flush=True)
        print(leer(arg), flush=True)
