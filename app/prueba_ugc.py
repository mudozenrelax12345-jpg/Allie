"""¿Puede Allie sujetar un producto sin que se le deformen las manos?

De esto depende si tiene sentido ofrecerla para vídeos de producto. El
generador que usamos tiene dos reglas escritas a fuego porque es donde peor
falla: que no sujete nada y que no abra la boca. Un vídeo de producto necesita
exactamente lo contrario, así que la pregunta no es si queremos hacerlo sino
si el generador da para ello.

Esto NO toca el banco ni publica nada. Genera un puñado de fotos con el
producto en la mano, con tres niveles de dificultad, las revisa y las deja en
videos/ugc/ para mirarlas con los ojos. Una tarde de respuesta en vez de
descubrirlo después de haberle dicho que sí a un cliente.

El producto es inventado y sin marca a propósito: ni imitamos a nadie ni le
pedimos al generador que dibuje letras, que tampoco sabe.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ajustes  # noqa: E402
import gemini  # noqa: E402
import reel  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
# Saltarse el revisor de manos: las fotos se guardan igual y se miran.
SIN_REVISOR = (os.environ.get("SIN_REVISOR") or "").strip().lower() in ("si", "sí", "true", "1")
SALIDA = BASE / "videos" / "ugc"
INFORME = SALIDA / "informe.json"

PRODUCTO = ajustes.texto(
    "PRODUCTO", "a plain unbranded amber glass dropper bottle, no label, no text")

# De menos a más difícil. Lo que de verdad se quiere saber es dónde se rompe,
# no si la más fácil sale bien.
ESCENAS = [
    ("1-cerca", "The same woman, upper-body shot sitting by a window in warm daylight, "
     f"holding {PRODUCTO} upright in one hand close to her chest, the bottle fully "
     "visible and in sharp focus, her other hand out of frame"),
    ("2-dos-manos", "The same woman, upper-body shot at a plain table in warm daylight, "
     f"holding {PRODUCTO} with both hands in front of her, fingers clearly visible "
     "and relaxed around the bottle"),
    ("3-senalando", "The same woman, upper-body shot in warm daylight, "
     f"holding {PRODUCTO} in one hand and pointing at it with the index finger of "
     "the other hand, both hands fully visible"),
    ("4-hablando", "The same woman, upper-body shot in warm daylight, "
     f"holding {PRODUCTO} up beside her face, mouth slightly open as if speaking "
     "to the camera, looking straight at the lens"),
]

# El revisor normal da por buena la boca cerrada y descarta la abierta. Para un
# vídeo de producto hablar es el objetivo, así que la última escena se juzga
# con otra vara: lo que importa son las manos y que sea ella.
MANOS = """Mira esta foto con MUCHA atención, ampliando mentalmente las manos.
Es para un vídeo de producto, así que lo único que la invalida son las manos y el
objeto. NO te fijes en si tiene la boca abierta ni en si está hablando: eso aquí
está permitido.

Responde "ok": false si ves cualquiera de estas cosas:
- dedos de más o de menos, dedos fusionados, torcidos o de largo imposible
- una mano con forma rara, mal articulada o pegada al objeto
- el objeto deformado, flotando, atravesado por un dedo o sujeto de una manera
  que no se sostiene físicamente
- texto, letras, logotipos o marcas inventadas sobre el objeto
- más de dos manos en la imagen

Devuelve SOLO un JSON: {"ok": true|false, "problema": "qué has visto, en español, muy breve"}"""


def log(m):
    print(f"· {m}", flush=True)


def main():
    p = reel.persona()
    SALIDA.mkdir(parents=True, exist_ok=True)
    for viejo in SALIDA.glob("*.jpg"):
        viejo.unlink()
    ref = reel.referencia_bytes(p)

    resultados = []
    for nombre, escena in ESCENAS:
        apunte = {"escena": nombre, "texto": escena, "intentos": []}
        for intento in range(3):
            try:
                datos, fallos = reel.kontext(escena, p)
            except reel.SinCuota as e:
                apunte["intentos"].append(f"sin cuota: {e}")
                log(f"{nombre}: sin cuota, corto aquí")
                resultados.append(apunte)
                guardar(resultados)
                return
            if datos is None:
                apunte["intentos"].append("no generó: " + " | ".join(fallos or ["?"]))
                time.sleep(reel.ESPERAS[min(intento, len(reel.ESPERAS) - 1)])
                continue

            f = SALIDA / f"{nombre}-{intento + 1}.jpg"
            f.write_bytes(datos)   # se guarda SIEMPRE, buena o mala: es la prueba

            # El revisor de manos es de Gemini, que se queda sin cuota a media
            # mañana. Para ESTA prueba no es imprescindible: las fotos se
            # guardan todas y se miran con los ojos, que es justamente el
            # punto. Sin él se generan las cuatro escenas y se juzgan después.
            if SIN_REVISOR:
                manos, ok_manos = {"problema": "no revisado"}, True
            else:
                try:
                    manos = gemini.json_(MANOS, imagenes=[datos, gemini._retrato(datos)])
                    ok_manos = bool(manos.get("ok"))
                except Exception as e:  # noqa: BLE001
                    manos, ok_manos = {"problema": f"no se pudo revisar: {e}"}, True
                    log(f"Sin revisor de manos ({e}); sigo y lo miramos a ojo")
            # La identidad NO se salta: la hace OpenCV y no gasta cuota.
            misma, detalle = (True, "sin referencia") if ref is None \
                else gemini._identidad(ref, datos)
            apunte["intentos"].append({
                "archivo": f.name, "manos_ok": ok_manos,
                "manos": (manos.get("problema") or "").strip(),
                "es_ella": misma, "identidad": detalle,
            })
            log(f"{nombre} intento {intento + 1}: manos "
                + ("bien" if ok_manos else "MAL · " + (manos.get('problema') or ''))
                + (" · es ella" if misma else " · NO ES ELLA"))
            if ok_manos and misma:
                apunte["sale"] = f.name
                break
            if SIN_REVISOR:
                break   # una por escena basta: lo que importa es verlas todas
            time.sleep(2)
        resultados.append(apunte)
        guardar(resultados)

    buenas = sum(1 for r in resultados if r.get("sale"))
    log(f"\n{buenas} de {len(ESCENAS)} escenas salieron bien")


def guardar(resultados):
    INFORME.write_text(json.dumps({
        "cuando": datetime.now(timezone.utc).isoformat(),
        "producto": PRODUCTO, "resultados": resultados,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · prueba_ugc\n\n"
            f"{detalle}\n", encoding="utf-8")
        sys.exit(1)
