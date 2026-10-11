"""¿De verdad no hay cupo de imágenes en Gemini, o me precipité?

El 9 de octubre di Gemini por descartado porque todos sus modelos de imagen
contestaron 429. De ahí salió la conclusión de que la única vía gratis era
Hugging Face, que da unas cuatro o cinco imágenes al día y nos tiene
ahogados. Pero un 429 puede ser dos cosas muy distintas: que la clave no
tenga acceso, o que ese día ya se hubiera gastado el cupo. No lo comprobé.

Y la diferencia es enorme: el nivel gratuito de Gemini está documentado en
cientos de imágenes al día, no cuatro.

Esto le pregunta a cada modelo por separado, con la foto de Allie como
referencia, y guarda lo que conteste cada uno palabra por palabra. Si algún
modelo devuelve una imagen, la guarda para poder mirarla y decidir si de
verdad conserva la cara, que es lo único que importa.

Deja videos/prueba-gemini/ con el informe y las imágenes.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402
import reel  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "videos" / "prueba-gemini"
INFORME = SALIDA / "informe.json"

# Todos los que puedan existir, uno por uno y sin memoria entre ellos: el
# imagen() normal se queda con el primero que funciona y descarta los demás
# para no gastar intentos, que está bien para producir pero no para averiguar.
MODELOS = [
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
    "gemini-3-pro-image",
    "gemini-3-pro-image-preview",
    "gemini-2.0-flash-preview-image-generation",
]

ESCENA = ("Keep her face, hair, skin tone and eye colour exactly as they are — it must "
          "be unmistakably the same woman. Place her sitting by a window in a Madrid "
          "flat wearing a cream knit sweater, warm afternoon light, upper-body shot, "
          "calm closed mouth, hands out of frame. Photorealistic smartphone photo. "
          "No text, no logos.")


def log(m):
    print(f"· {m}", flush=True)


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    p = reel.persona()
    ref = reel.referencia_bytes(p)
    if ref is None:
        raise SystemExit("No se pudo traer la foto de referencia")

    resultados = []
    for modelo in MODELOS:
        # Se llama al modelo directamente, sin la lista de descartados, para
        # que el veredicto de uno no tape a los demás.
        gemini._img_elegido = None
        gemini._img_descartados.clear()
        guardado = gemini.IMG_MODELOS[:]
        gemini.IMG_MODELOS[:] = [modelo]
        try:
            datos, dichos = gemini.imagen(ESCENA, ref)
        except Exception as e:  # noqa: BLE001
            datos, dichos = None, [f"{type(e).__name__}: {str(e)[:200]}"]
        finally:
            gemini.IMG_MODELOS[:] = guardado

        if datos:
            f = SALIDA / f"{modelo}.jpg"
            f.write_bytes(datos)
            misma, detalle = gemini.misma_persona(ref, datos)
            resultados.append({"modelo": modelo, "imagen": f.name,
                               "bytes": len(datos), "es_ella": misma,
                               "identidad": detalle})
            log(f"{modelo}: IMAGEN ({len(datos)//1024} KB) · "
                + ("es ella" if misma else "NO es ella") + f" · {detalle}")
        else:
            resultados.append({"modelo": modelo, "imagen": None,
                               "dijo": "; ".join(dichos or ["sin motivo"])})
            log(f"{modelo}: {'; '.join(dichos or ['sin motivo'])[:200]}")

        INFORME.write_text(json.dumps({
            "cuando": datetime.now(timezone.utc).isoformat(),
            "escena": ESCENA, "resultados": resultados,
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    funcionan = [r for r in resultados if r.get("imagen")]
    log(f"\n{len(funcionan)} de {len(MODELOS)} modelos devolvieron imagen")
    if funcionan:
        log("Hay vía alternativa a Hugging Face. Mirar las imágenes antes de decidir.")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · probar_gemini\n\n"
            f"{detalle}\n", encoding="utf-8")
        sys.exit(1)
