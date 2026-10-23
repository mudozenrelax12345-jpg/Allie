"""Comprueba el reel de lista en las dos redes y con voz, sin usar Kokoro.

DE DÓNDE SALE ESTA PRUEBA. El 22 de octubre la rama con narración reventó en
GitHub con un UnboundLocalError: usaba `titulo` antes de crearlo. Un fallo de
cinco segundos de arreglar que costó una ejecución entera de ocho minutos,
porque Kokoro solo está en la máquina de GitHub y en local yo solo podía
probar la rama muda. Una rama que no se puede probar es una rama que se
rompe.

Así que aquí la voz se finge: duraciones plausibles y un wav de silencio.
Todo lo demás —el reparto de planos, el dibujo de las fichas, las zonas
seguras, el montaje con ffmpeg— es el de verdad. Y al final se MIRA EL
FICHERO que sale, no el código.

Lo que se exige, y por qué:

  · Que las dos plataformas monten, con voz y sin ella. Cuatro combinaciones.
  · Que el texto no se salga de la zona segura. En TikTok la columna de
    botones se come 140 píxeles del margen derecho y el pie sube hasta 1440:
    un texto que en Instagram se lee entero, allí queda debajo del botón de
    compartir.
  · Que la portada quepa ENTERA, título y frase de gancho. En la primera
    versión de TikTok el título ocupaba tres líneas y el programa descartaba
    —correctamente— la línea que daba el motivo para quedarse.
  · Que el vídeo mida 1080×1920 y lleve pista de audio: Instagram rechaza un
    vídeo sin ella.
  · Que las fotos vuelvan al banco. Un ensayo no gasta material.
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
BASE = APP.parent

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que + (f" · {detalle}" if detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


def pieza_con_fotos():
    """Una pieza de la cola cuya etiqueta tenga al menos tres fotos libres."""
    from collections import Counter
    d = json.loads((BASE / "banco" / "indice.json").read_text(encoding="utf-8"))
    fotos = d if isinstance(d, list) else d.get("fotos", [])
    hay = Counter(x.get("etiqueta") for x in fotos
                  if not x.get("usada") and not x.get("retirada"))
    cola = json.loads((BASE / "contenido" / "cola.json").read_text(encoding="utf-8"))
    for p in cola.get("piezas", []):
        if p.get("imagenes"):
            continue          # las piezas con imágenes propias no usan banco
        if hay.get(p.get("etiqueta"), 0) >= 3:
            return p["id"]
    raise SystemExit("Ninguna pieza de la cola tiene tres fotos libres de su "
                     "etiqueta. Llena el banco antes de pasar esta prueba:\n"
                     f"   libres por etiqueta: {dict(hay)}")


def libres():
    d = json.loads((BASE / "banco" / "indice.json").read_text(encoding="utf-8"))
    f = d if isinstance(d, list) else d.get("fotos", [])
    return sum(1 for x in f if not x.get("usada") and not x.get("retirada"))


def voz_fingida(portada, fichas, cierre, destino_wav):
    """Lo que devolvería Kokoro: una duración por plano y un wav."""
    frases = [portada] + [f"{x['nombre']}. {x['calle']}." for x in fichas] + [cierre]
    # 14 caracteres por segundo es el ritmo de una voz leyendo en español.
    duraciones = [max(len(f) / 14 + 0.45, 3.2) for f in frases]
    destino_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino_wav), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * int(24000 * sum(duraciones)))
    return duraciones


def sondear(mp4):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=width,height,codec_type:format=duration", "-of", "json", str(mp4)],
        capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def una(plataforma, con_voz, antes):
    import importlib
    import os
    os.environ["PLATAFORMA"] = plataforma
    os.environ["VOZ"] = "ef_dora" if con_voz else ""
    os.environ["EN_SECO"] = "si"
    # LA PIEZA SE ELIGE POR LO QUE HAY EN EL BANCO, no a dedo.
    #
    # Estaba fija en «madrid-librerias-cafe», cuya etiqueta es «cafe». El 23
    # de octubre esa etiqueta se quedó sin fotos libres y las cuatro
    # comprobaciones empezaron a fallar sin que nada estuviera roto. Es la
    # tercera vez en esta sesión que una prueba depende del estado de
    # producción: con el gasto de Cloudflare, con la carpeta de salida, y
    # ahora con el banco.
    os.environ["PIEZA"] = pieza_con_fotos()
    import reel_lista
    importlib.reload(reel_lista)
    if con_voz:
        reel_lista.narrar_fichas = voz_fingida

    etiqueta = f"{plataforma}{' con voz' if con_voz else ' mudo'}"
    try:
        final = reel_lista.main()
    except Exception as e:  # noqa: BLE001
        comprobar(f"{etiqueta}: monta", False, f"{type(e).__name__}: {e}")
        return
    comprobar(f"{etiqueta}: monta", final is not None and Path(final).exists())
    if not final:
        return

    s = sondear(final)
    v = next((x for x in s.get("streams", []) if x.get("codec_type") == "video"), {})
    a = next((x for x in s.get("streams", []) if x.get("codec_type") == "audio"), {})
    dur = float(s.get("format", {}).get("duration", 0))
    comprobar(f"{etiqueta}: mide 1080×1920",
              (v.get("width"), v.get("height")) == (1080, 1920),
              f"{v.get('width')}×{v.get('height')}")
    comprobar(f"{etiqueta}: lleva audio", bool(a),
              "Instagram rechaza un vídeo sin pista de audio")
    comprobar(f"{etiqueta}: dura entre 20 y 60s", 20 <= dur <= 60, f"{dur:.1f}s")
    comprobar(f"{etiqueta}: las fotos vuelven al banco", libres() == antes,
              f"antes {antes}, ahora {libres()}")
    Path(final).unlink(missing_ok=True)


def zonas_seguras():
    """Que nada de lo que se dibuja se salga de donde se puede dibujar."""
    import importlib
    import os
    from PIL import ImageDraw, ImageFont
    for plataforma, suelo, margen_der in (("instagram", 1550, 70), ("tiktok", 1440, 170)):
        os.environ["PLATAFORMA"] = plataforma
        import reel_lista
        importlib.reload(reel_lista)
        comprobar(f"{plataforma}: el suelo es {suelo}", reel_lista.SUELO == suelo)
        comprobar(f"{plataforma}: margen derecho {margen_der}",
                  reel_lista.MARGEN_DER == margen_der)

        # La portada más larga que puede tocar: título de la pieza + gancho.
        d = ImageDraw.Draw(__import__("PIL.Image", fromlist=["Image"]).new("RGB", (1080, 1920)))
        ancho = 1080 - 70 - reel_lista.MARGEN_DER
        titulo = "Librerías de Madrid donde además puedes sentarte a tomar algo"
        pie = "Apunta los horarios: varias cierran a mediodía y es el clásico viaje en balde"
        f_p = ImageFont.truetype(reel_lista.NORMAL, 42)
        lineas_pie = reel_lista.envolver(d, pie, f_p, ancho)
        f_t = ImageFont.truetype(reel_lista.NEGRITA, 84)
        lineas = reel_lista.envolver(d, titulo, f_t, ancho)
        alto_pie = len(lineas_pie) * 50 + 20
        while f_t.size > 46 and (len(lineas) * (f_t.size + 14) + alto_pie) > (
                reel_lista.SUELO - reel_lista.TEXTO_Y + 110):
            f_t = ImageFont.truetype(reel_lista.NEGRITA, f_t.size - 6)
            lineas = reel_lista.envolver(d, titulo, f_t, ancho)
        alto = len(lineas) * (f_t.size + 14) + alto_pie
        arriba = reel_lista.SUELO - alto
        comprobar(f"{plataforma}: la portada entera cabe en la zona segura",
                  arriba > 950 and reel_lista.SUELO <= suelo,
                  f"el bloque va de {arriba} a {reel_lista.SUELO}")
        comprobar(f"{plataforma}: la frase de gancho se dibuja", len(lineas_pie) > 0,
                  f"{len(lineas_pie)} líneas de gancho")
        mas_ancho = max(d.textbbox((0, 0), l, font=f_t)[2] for l in lineas)
        comprobar(f"{plataforma}: el título no invade la columna de botones",
                  70 + mas_ancho <= 1080 - margen_der,
                  f"llega a {70 + mas_ancho} y el límite es {1080 - margen_der}")


def main():
    antes = libres()
    print(f"{antes} fotos libres en el banco\n", flush=True)
    zonas_seguras()
    print(flush=True)
    for plataforma in ("instagram", "tiktok"):
        for con_voz in (False, True):
            una(plataforma, con_voz, antes)
    print(flush=True)
    comprobar("el banco queda como estaba", libres() == antes,
              f"antes {antes}, ahora {libres()}")

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nel reel de lista funciona en las dos redes, con voz y sin ella", flush=True)


if __name__ == "__main__":
    main()
