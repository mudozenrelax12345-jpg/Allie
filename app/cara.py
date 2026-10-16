"""Comprobar que la de la foto es Allie, sin gastar una sola llamada a nadie.

POR QUÉ. Hasta hoy la identidad la juzgaba Gemini: se le mandaban cuatro
imágenes y se le preguntaba «¿es la misma mujer?». Eso tiene dos problemas.

El primero es la cuota. El 16 de octubre Gemini se quedó seco a media mañana
—«Your project has exceeded a quota»— y el reel del día no se montó. La
comprobación de identidad es, con diferencia, lo que más consume: cuatro
imágenes por foto generada.

El segundo es que un modelo de lenguaje es la herramienta equivocada. Ya se
equivocó una vez, el 11 de octubre: dijo que una mujer de ojos marrones «es
ella», y solo dejó de hacerlo cuando se le empezaron a mandar recortes
ampliados de la cara. Comparar dos caras no es una tarea de conversación: es
medir la distancia entre dos vectores, y para eso hay modelos pequeños,
deterministas y hechos para esto.

CÓMO. Dos modelos de OpenCV, ambos diminutos:
  · YuNet, 230 KB, encuentra las caras y sus cinco puntos de referencia.
  · SFace, 37 MB, convierte una cara alineada en 128 números.
Dos caras de la misma persona dan un coseno alto entre sus vectores. OpenCV
recomienda 0,363 como frontera; aquí se usa algo más exigente, porque
publicar a otra persona cuesta mucho más que perder una foto.

Esto no sustituye a la revisión de CALIDAD (manos, dientes, deformidades),
que sigue haciendo Gemini: solo responde a «¿es ella?», que es la pregunta
cuya respuesta equivocada no tiene arreglo una vez publicada.
"""
import os
import urllib.request
from io import BytesIO
from pathlib import Path

import numpy as np

CACHE = Path(os.environ.get("CARA_CACHE") or "/tmp/modelos-cara")

# Varias direcciones por modelo: si GitHub cambia de sitio los ficheros, que
# no se caiga la comprobación entera y con ella el reel del día.
FUENTES = {
    "detector": (
        "face_detection_yunet_2023mar.onnx",
        ["https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/"
         "face_detection_yunet/face_detection_yunet_2023mar.onnx",
         "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
         "face_detection_yunet/face_detection_yunet_2023mar.onnx"]),
    "rasgos": (
        "face_recognition_sface_2021dec.onnx",
        ["https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/"
         "face_recognition_sface/face_recognition_sface_2021dec.onnx",
         "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
         "face_recognition_sface/face_recognition_sface_2021dec.onnx"]),
}

# OpenCV recomienda 0,363 para «es la misma persona». Aquí se usa 0,50, y
# el número sale de medir, no de elegirlo a ojo:
#   · las fotos buenas de Allie puntúan entre 0,56 y 0,80
#   · la desconocida que llegó a publicarse una semana puntúa 0,411
# Con 0,42 la desconocida se quedaba fuera por nueve milésimas, que no es un
# margen: cualquier cara parecida del futuro entraría. Con 0,50 hay 0,09 de
# hueco por debajo y 0,06 por encima.
#
# Y los dos errores no cuestan lo mismo: descartar una foto buena cuesta ocho
# segundos de Cloudflare y hay noventa al día; publicar a otra mujer en la
# cuenta de Allie no se arregla.
UMBRAL = float(os.environ.get("CARA_UMBRAL") or 0.50)

_detector = None
_rasgos = None


class SinCara(RuntimeError):
    """No se encontró ninguna cara donde tenía que haberla."""


def _fichero(clave):
    nombre, urls = FUENTES[clave]
    destino = CACHE / nombre
    if destino.exists() and destino.stat().st_size > 10_000:
        return destino
    CACHE.mkdir(parents=True, exist_ok=True)
    quejas = []
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                datos = r.read()
            # Un puntero de Git LFS pesa unos cientos de bytes y empieza por
            # «version https://git-lfs». Si cae eso en vez del modelo, el
            # error que da OpenCV después no hay quien lo entienda.
            if len(datos) < 10_000 or datos[:7] == b"version":
                quejas.append(f"{url}: vinieron {len(datos)} bytes, no es el modelo")
                continue
            destino.write_bytes(datos)
            return destino
        except Exception as e:  # noqa: BLE001
            quejas.append(f"{url}: {type(e).__name__}: {str(e)[:120]}")
    raise RuntimeError(f"No pude traer el modelo {nombre}: " + " | ".join(quejas))


def _motores():
    global _detector, _rasgos
    if _detector is None or _rasgos is None:
        import cv2
        _detector = cv2.FaceDetectorYN.create(str(_fichero("detector")), "", (320, 320),
                                              score_threshold=0.7)
        _rasgos = cv2.FaceRecognizerSF.create(str(_fichero("rasgos")), "")
    return _detector, _rasgos


def hay():
    """¿Se puede usar esto? Sin cv2 o sin modelos, se vuelve a Gemini."""
    try:
        import cv2  # noqa: F401
        _motores()
        return True
    except Exception:  # noqa: BLE001
        return False


def _imagen(datos):
    import cv2
    arr = np.frombuffer(datos, np.uint8)
    im = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if im is None:
        raise SinCara("no se pudo abrir la imagen")
    return im


def rasgo(datos):
    """Los 128 números de la cara más grande de la foto.

    La más grande, no la primera: en una cafetería salen desconocidos de
    fondo, y comparar la cara de un señor borroso con la referencia daría un
    «no es ella» que no significa nada.
    """
    import cv2
    detector, rasgos = _motores()
    im = _imagen(datos)
    alto, ancho = im.shape[:2]
    detector.setInputSize((ancho, alto))
    _, caras = detector.detect(im)
    if caras is None or len(caras) == 0:
        raise SinCara("no se ve ninguna cara en la foto")
    # columnas 2 y 3 son ancho y alto del recuadro
    mayor = max(caras, key=lambda c: float(c[2]) * float(c[3]))
    alineada = rasgos.alignCrop(im, mayor)
    v = rasgos.feature(alineada).flatten().astype(np.float64)
    return v / (np.linalg.norm(v) + 1e-9), len(caras)


def misma_persona(referencia, foto, umbral=None):
    """(es_ella, parecido, explicación). Falla cerrado: duda = no.

    `referencia` y `foto` son bytes JPEG/PNG.
    """
    u = UMBRAL if umbral is None else umbral
    try:
        a, _ = rasgo(referencia)
    except SinCara as e:
        # Si la referencia no tiene cara, el problema es de configuración, no
        # de esta foto. Que se note en vez de rechazarlo todo en silencio.
        raise RuntimeError(f"La foto de referencia de Allie no sirve: {e}") from e
    try:
        b, cuantas = rasgo(foto)
    except SinCara as e:
        return False, 0.0, f"no se puede comprobar quién es: {e}"
    parecido = float(np.dot(a, b))
    if parecido >= u:
        return True, parecido, f"es ella (parecido {parecido:.3f} ≥ {u})"
    return False, parecido, (f"NO es ella: parecido {parecido:.3f}, por debajo de "
                             f"{u}" + (f" (había {cuantas} caras)" if cuantas > 1 else ""))
