"""Comprueba el formato «dato» sin necesitar la máquina de voz.

Mismo motivo que la prueba del otro formato: Kokoro y Piper solo están en
la máquina de GitHub, así que en local la rama con voz no se podía probar
y se rompía allí. Aquí la voz se finge y todo lo demás es de verdad.

Lo que se exige, y por qué cada cosa:

  · Que monte en las dos redes.
  · Que el texto APAREZCA POR TROZOS. Es el cambio entero de este formato:
    si el texto saliera de golpe estaríamos donde estábamos. Se mide
    contando píxeles de letra en tres momentos del mismo plano: tienen que
    ir a más.
  · Que la foto se mueva y que el texto no.
  · Que LLEVE MÚSICA. Los vídeos anteriores iban sobre silencio absoluto y
    eso es lo que más los delataba. Se comprueba que suena algo en los
    huecos en los que la voz calla.
  · Que nada invada la zona de los botones ni el pie de la aplicación.
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
BASE = APP.parent

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que + (f" · {detalle}" if detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


def voz_fingida(portada, fichas, cierre, destino_wav, formato="lista"):
    frases = [portada] + [x["nombre"] for x in fichas] + [cierre]
    duraciones = [max(len(f) / 14 + 0.45, 3.4) for f in frases]
    destino_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino_wav), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        n = int(24000 * sum(duraciones))
        t = np.arange(n) / 24000
        # Una onda floja hace de voz: loudnorm necesita algo que normalizar.
        onda = (np.sin(2 * np.pi * 180 * t) * 0.08 * 32767).astype("<i2")
        w.writeframes(onda.tobytes())
    return duraciones


def foto(mp4, t, escala=1):
    p = BASE / "video" / f"_t{t}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(mp4),
                    "-frames:v", "1", str(p), "-y"], check=False)
    if not p.exists():
        return None
    from PIL import Image
    a = np.asarray(Image.open(p).convert("L"), dtype=float)
    p.unlink(missing_ok=True)
    return a


def libres():
    d = json.loads((BASE / "banco" / "indice.json").read_text(encoding="utf-8"))
    f = d if isinstance(d, list) else d.get("fotos", [])
    return sum(1 for x in f if not x.get("usada") and not x.get("retirada"))


def una(plataforma, antes):
    import importlib
    import os
    os.environ["PLATAFORMA"] = plataforma
    os.environ["EN_SECO"] = "si"
    os.environ["SIN_RED"] = "si"
    os.environ["PIEZA"] = "comida-datos"
    import reel_lista
    importlib.reload(reel_lista)
    import reel_dato
    importlib.reload(reel_dato)
    reel_dato.rl.narrar_fichas = voz_fingida

    et = plataforma
    try:
        final = reel_dato.main()
    except Exception as e:  # noqa: BLE001
        comprobar(f"{et}: monta", False, f"{type(e).__name__}: {e}")
        return
    comprobar(f"{et}: monta", final is not None and Path(final).exists())
    if not final:
        return

    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=width,height,codec_type:format=duration",
                        "-of", "json", str(final)], capture_output=True, text=True)
    s = json.loads(r.stdout or "{}")
    v = next((x for x in s.get("streams", []) if x.get("codec_type") == "video"), {})
    a = next((x for x in s.get("streams", []) if x.get("codec_type") == "audio"), {})
    dur = float(s.get("format", {}).get("duration", 0))
    comprobar(f"{et}: mide 1080×1920",
              (v.get("width"), v.get("height")) == (1080, 1920))
    comprobar(f"{et}: lleva audio", bool(a))
    comprobar(f"{et}: dura entre 20 y 45s", 20 <= dur <= 45, f"{dur:.1f}s")

    # EL TEXTO SE ESCRIBE SOLO. Tres instantes del mismo plano: la cantidad
    # de píxeles de letra tiene que ir creciendo. Es LA comprobación de este
    # formato: si saliera de golpe, no habría cambiado nada respecto a lo
    # que Teresa llamó «una mierda de vídeo».
    reg = json.loads((BASE / "video" / "ultimo-dato.json").read_text(encoding="utf-8"))
    ds = reg.get("duraciones") or []
    if len(ds) >= 3:
        ini = ds[0]                      # termina la portada
        momentos = [ini + ds[1] * f for f in (0.20, 0.55, 0.92)]
    else:
        momentos = [5.2, 6.2, 7.4]
    cuentas = []
    for t in momentos:
        im = foto(final, t)
        if im is None:
            break
        cuentas.append(int((im[900:1450] > 200).sum()))
    if len(cuentas) == 3:
        comprobar(f"{et}: el texto aparece por trozos",
                  cuentas[0] < cuentas[1] <= cuentas[2] and cuentas[0] > 0,
                  " → ".join(str(c) for c in cuentas) + " píxeles de letra en "
                  + ", ".join(f"{m:.1f}s" for m in momentos))

    import medir_movimiento
    # LA VENTANA TIENE QUE CABER ENTERA EN MEDIA FICHA. A mitad de plano
    # el encuadre salta —es el corte que trae este formato— y medir a
    # caballo del salto da cifras sin sentido: 8,8 px/s antes, 85 al
    # cruzarlo, 18,8 después. Se mide dentro de la primera mitad.
    a = ini + ds[1] * 0.15
    px = medir_movimiento.por_segundo(final, a, a + 0.8, alto=slice(100, 760))
    if px is not None:
        comprobar(f"{et}: la foto se mueve", px >= 8.0, f"{px:.1f} px/s")

    # MÚSICA. Se mide el nivel del medio segundo final, donde la voz ya ha
    # terminado: si allí no suena nada, el vídeo va sobre silencio.
    rms = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", f"{max(dur - 0.8, 0):.2f}", "-i", str(final),
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    medio = next((float(l.split(":")[1].split("dB")[0])
                  for l in rms.splitlines() if "mean_volume" in l), -99)
    comprobar(f"{et}: suena música y no silencio", medio > -50,
              f"{medio:.1f} dB al final, cuando la voz ya ha callado")

    comprobar(f"{et}: las fotos vuelven al banco", libres() == antes,
              f"antes {antes}, ahora {libres()}")
    Path(final).unlink(missing_ok=True)


def zona_segura():
    """Que ninguna letra entre en la columna de botones ni baje del suelo."""
    import importlib
    import os
    from PIL import Image
    for plataforma, suelo, margen_der in (("tiktok", 1430, 170),
                                          ("instagram", 1540, 70)):
        os.environ["PLATAFORMA"] = plataforma
        import reel_dato
        importlib.reload(reel_dato)
        ficha = {"n": "1", "nombre": "La tortilla de patatas aparece por escrito en 1817",
                 "calle": "En una carta a las Cortes de Navarra. Decía que en Pamplona "
                          "se hacía con dos huevos y cinco patatas.", "horario": "",
                 "formato": "dato"}
        png = BASE / "video" / "_zona.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        reel_dato.pintar(None, ficha, 5, 999, True, png)
        a = np.asarray(Image.open(png).convert("L"), dtype=float)
        png.unlink(missing_ok=True)
        letras = a > 200
        cols = np.where(letras.any(axis=0))[0]
        filas = np.where(letras.any(axis=1))[0]
        comprobar(f"{plataforma}: el texto no invade los botones",
                  len(cols) and cols.max() <= W_LIM(margen_der),
                  f"llega a {cols.max() if len(cols) else 0}, límite {W_LIM(margen_der)}")
        comprobar(f"{plataforma}: el texto no baja del suelo",
                  len(filas) and filas.max() <= suelo,
                  f"baja hasta {filas.max() if len(filas) else 0}, suelo {suelo}")


def W_LIM(margen_der):
    return 1080 - margen_der


def main():
    antes = libres()
    print(f"{antes} fotos libres\n", flush=True)
    zona_segura()
    print(flush=True)
    for plataforma in ("tiktok", "instagram"):
        una(plataforma, antes)
    print(flush=True)
    comprobar("el banco queda como estaba", libres() == antes)
    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nel formato dato funciona", flush=True)


if __name__ == "__main__":
    main()
