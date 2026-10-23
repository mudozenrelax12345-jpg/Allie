"""El formato «dato», montado como un vídeo corto y no como una diapositiva.

DE DÓNDE SALE. Teresa, dos veces seguidas y sobre dos vídeos distintos:
«vaya mierda de vídeo, currátelo más». Tenía razón las dos veces, y la
segunda vez ya no era por las fotos —esas estaban arregladas— sino por la
forma. Lo que le estaba mandando era:

    una foto quieta · un párrafo gris pegado abajo · una voz encima
    de SILENCIO ABSOLUTO · un corte cada cuatro segundos

Eso no es un vídeo corto, es una presentación con voz en off. Cambiarle el
zoom o la foto no lo arregla, porque el problema no está en los ajustes.

LO QUE CAMBIA AQUÍ, y por qué cada cosa:

  · MÚSICA. Ninguno de los anteriores llevaba. Una voz sobre silencio se
    percibe como un fallo técnico antes de que te dé tiempo a entender de
    qué va el vídeo. La base se sintetiza en app/musica.py y va diez
    decibelios por debajo de la voz.

  · EL TEXTO ES EL PROTAGONISTA, no un pie. Antes era un párrafo de cuerpo
    62 en una caja gris al fondo de la pantalla, que es donde el ojo mira
    en último lugar. Ahora va grande, en el centro, y APARECE POR TROZOS
    al ritmo de la voz. Texto que se construye delante de ti es movimiento
    aunque la foto no se mueva: es lo que hace que no puedas apartar la
    vista.

  · LA CIFRA, RESALTADA. El dato de cada ficha casi siempre es un número
    —1817, 1524, el siglo XVI— y es lo único que la gente va a recordar.
    Va en color.

  · UN CORTE A MITAD DE FICHA. Cuatro segundos de la misma imagen son
    demasiados. A mitad de plano el encuadre salta: la misma foto, más
    cerca. Cambiar de plano cada dos segundos sostiene la atención muy por
    encima de un plano fijo.

LO QUE NO CAMBIA, porque ya estaba bien: las fotos reales de cada cosa con
licencia libre (app/lugares.py), las zonas seguras de cada red, y que la
voz lea el titular mientras el detalle se queda para los ojos.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
BASE = Path(__file__).resolve().parent.parent

import reel_lista as rl  # noqa: E402

W, H, FPS = 1080, 1920, 30
TRABAJO = BASE / "video" / "dato"
SALIDA = BASE / "videos"

PLATAFORMA = (os.environ.get("PLATAFORMA") or "tiktok").strip().lower()
if PLATAFORMA == "tiktok":
    SUELO, MARGEN_DER = 1430, 170
else:
    SUELO, MARGEN_DER = 1540, 70
MARGEN = 72
ANCHO = W - MARGEN - MARGEN_DER

NEGRITA = rl.NEGRITA
NORMAL = rl.NORMAL
CLARO = (252, 252, 252)
ACENTO = (255, 196, 61)

TAM_TITULAR = 86
TAM_DETALLE = 42
TAM_CONTADOR = 34


def log(m):
    print(f"· {m}", flush=True)


# ─────────────────────────────────────────────── imagen
def foto_plena(ruta):
    """La foto ocupando los 1080×1920 enteros, recortada centrada.

    A pantalla completa y no en un hueco con fondo desenfocado: una foto
    metida en una caja con bordes borrosos es el aspecto de las plantillas
    de hace diez años, y además desperdicia media pantalla.
    """
    src = Image.open(ruta).convert("RGB")
    e = max(W / src.width, H / src.height)
    gr = src.resize((max(W, int(src.width * e)), max(H, int(src.height * e))),
                    Image.LANCZOS)
    cx, cy = (gr.width - W) // 2, (gr.height - H) // 2
    return gr.crop((cx, cy, cx + W, cy + H))


def sombra():
    """Oscurecer arriba y abajo para que el texto se lea sobre cualquier foto.

    Arriba poco, solo para separar del borde; abajo bastante, que es donde
    vive el texto. En el medio no se toca: ahí tiene que verse la foto.
    """
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    for i in range(300):
        d.rectangle([0, i, W, i + 1], fill=(8, 8, 10, int(110 * (1 - i / 300) ** 1.4)))
    arranque = 760
    for i in range(H - arranque):
        a = int(225 * min(1.0, (i / 420) ** 0.85))
        d.rectangle([0, arranque + i, W, arranque + i + 1], fill=(8, 8, 10, a))
    return capa


# ─────────────────────────────────────────────── texto
def trozos(titular, por_trozo=3):
    """El titular partido en grupos de palabras, como se dice en alto."""
    palabras = titular.split()
    return [" ".join(palabras[i:i + por_trozo])
            for i in range(0, len(palabras), por_trozo)]


def es_cifra(p):
    """Si una palabra es el dato: un número, un año, un siglo."""
    limpia = p.strip(".,;:«»\"'()")
    return bool(re.search(r"\d", limpia)) or limpia in (
        "XVI", "XVII", "XVIII", "XIX", "XX", "II", "III", "IV", "V")


def lineas_de(d, texto, fuente):
    return rl.envolver(d, texto, fuente, ANCHO)


def pintar(foto_ignorada, ficha, total, visible, detalle_visible, destino):
    """Una capa de texto: el titular hasta «visible» palabras, y el detalle.

    Devuelve solo la capa transparente. El fondo va aparte porque se mueve
    y el texto no: si el texto viajase con el zoom se saldría de la zona
    segura, que en TikTok está a seis píxeles.
    """
    capa = sombra()
    d = ImageDraw.Draw(capa)

    titular = rl.sin_emoji(ficha["nombre"])
    palabras = titular.split()
    mostradas = " ".join(palabras[:visible])

    f_t = ImageFont.truetype(NEGRITA, TAM_TITULAR)
    lineas_tot = lineas_de(d, titular, f_t)
    while len(lineas_tot) > 3 and f_t.size > 54:
        f_t = ImageFont.truetype(NEGRITA, f_t.size - 5)
        lineas_tot = lineas_de(d, titular, f_t)
    alto_tit = len(lineas_tot) * (f_t.size + 12)

    f_d = ImageFont.truetype(NORMAL, TAM_DETALLE)
    detalle = rl.sin_emoji(ficha.get("calle") or "")
    lineas_det = lineas_de(d, detalle, f_d)[:3] if detalle else []
    alto_det = (len(lineas_det) * 52 + 24) if lineas_det else 0

    # EL BLOQUE NO SE MUEVE SEGÚN SE ESCRIBE. Se reserva desde el principio
    # el sitio del titular completo y el detalle va debajo. Si el bloque se
    # recolocase en cada trozo, el texto daría saltos y sería ilegible.
    y0 = SUELO - alto_det - alto_tit
    d.text((MARGEN, y0 - 52), f"{ficha['n']} de {total}",
           font=ImageFont.truetype(NEGRITA, TAM_CONTADOR), fill=ACENTO)

    # Dibujar palabra a palabra para poder colorear las cifras.
    y = y0
    puestas = 0
    for linea in lineas_tot:
        x = MARGEN
        for p in linea.split():
            if puestas >= len(mostradas.split()):
                break
            color = ACENTO if es_cifra(p) else CLARO
            d.text((x, y), p, font=f_t, fill=color)
            x += d.textlength(p + " ", font=f_t)
            puestas += 1
        y += f_t.size + 12
        if puestas >= len(mostradas.split()):
            break

    if detalle_visible:
        y = y0 + alto_tit + 16
        for ln in lineas_det:
            d.text((MARGEN, y), ln, font=f_d, fill=(226, 226, 230))
            y += 52

    capa.save(destino)
    return destino


def pintar_cartel(titulo, pie, destino, visible=None):
    capa = sombra()
    d = ImageDraw.Draw(capa)
    titulo, pie = rl.sin_emoji(titulo), rl.sin_emoji(pie or "")
    f_t = ImageFont.truetype(NEGRITA, 96)
    lineas = lineas_de(d, titulo, f_t)
    f_p = ImageFont.truetype(NORMAL, 44)
    lineas_pie = lineas_de(d, pie, f_p) if pie else []
    alto_pie = len(lineas_pie) * 54 + 22 if lineas_pie else 0
    while f_t.size > 54 and len(lineas) * (f_t.size + 14) + alto_pie > 620:
        f_t = ImageFont.truetype(NEGRITA, f_t.size - 6)
        lineas = lineas_de(d, titulo, f_t)
    alto = len(lineas) * (f_t.size + 14) + alto_pie
    y = SUELO - alto
    total_palabras = len(titulo.split())
    tope = total_palabras if visible is None else visible
    puestas = 0
    for linea in lineas:
        x = MARGEN
        for p in linea.split():
            if puestas >= tope:
                break
            d.text((x, y), p, font=f_t,
                   fill=ACENTO if es_cifra(p) else CLARO)
            x += d.textlength(p + " ", font=f_t)
            puestas += 1
        y += f_t.size + 14
        if puestas >= tope:
            break
    if puestas >= total_palabras:
        for ln in lineas_pie:
            d.text((MARGEN, y + 10), ln, font=f_p, fill=ACENTO)
            y += 54
    capa.save(destino)
    return destino


# ─────────────────────────────────────────────── montaje
def plano(fondo_jpg, capas, dur, destino, acerca=True):
    """Un plano: la foto se mueve, el texto aparece por trozos encima.

    «capas» son pares (png, desde_segundo). Cada capa se enseña desde su
    instante hasta que entra la siguiente, así que el texto se va
    construyendo. Y a mitad de plano el encuadre SALTA: mismo sitio, más
    cerca. Es un corte sin cambiar de foto, y evita que cuatro segundos
    sean cuatro segundos de lo mismo.
    """
    fot = max(2, int(dur * FPS))
    mitad = fot // 2
    R = 0.20
    if acerca:
        z = (f"if(gt(on,{mitad}),{1 + R * 1.45}+{R}*on/{fot},"
             f"1.0+{R}*on/{fot})")
        x = f"(iw-iw/zoom)*(0.34+0.32*on/{fot})"
    else:
        z = (f"if(gt(on,{mitad}),{1 + R * 1.45}+{R}*(1-on/{fot}),"
             f"{1 + R}-{R}*on/{fot})")
        x = f"(iw-iw/zoom)*(0.66-0.32*on/{fot})"
    cadena = [f"[0:v]scale={W*2}:-1,zoompan=z='{z}':d={fot}:x='{x}':"
              f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}[v0]"]
    entradas = ["-loop", "1", "-i", str(fondo_jpg)]
    for i, (png, _) in enumerate(capas):
        entradas += ["-loop", "1", "-i", str(png)]
    for i, (png, desde) in enumerate(capas):
        hasta = capas[i + 1][1] if i + 1 < len(capas) else dur + 1
        cadena.append(f"[v{i}][{i+1}:v]overlay=0:0:"
                      f"enable='between(t,{desde:.3f},{hasta:.3f})'[v{i+1}]")
    ultima = f"[v{len(capas)}]"
    cadena.append(f"{ultima}format=yuv420p,setsar=1[vf]")
    rl.ff(*entradas, "-t", f"{dur:.3f}", "-filter_complex", ";".join(cadena),
          "-map", "[vf]", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "20", "-r", str(FPS), str(destino))


def reparto(dur, n_trozos):
    """Cuándo entra cada trozo de texto dentro del plano.

    El primero entra enseguida —si el plano empieza vacío, el espectador
    ve una foto sin nada y se va— y los demás se reparten por el primer
    sesenta por ciento, para que el último se pueda leer con calma.
    """
    if n_trozos <= 1:
        return [0.0]
    util = dur * 0.74
    return [round(0.12 + util * i / n_trozos, 3) for i in range(n_trozos)]


def main():
    seco = (os.environ.get("EN_SECO") or "").strip().lower() in ("si", "sí", "true", "1")
    cola = json.loads((BASE / "contenido" / "cola.json").read_text(encoding="utf-8"))
    pedido = (os.environ.get("PIEZA") or "").strip()
    pieza = next((p for p in cola["piezas"]
                  if (p["id"] == pedido if pedido
                      else p.get("formato") == "dato" and not p.get("usado"))), None)
    if not pieza:
        raise RuntimeError("No hay pieza de formato «dato».")
    log(f"Pieza: {pieza['id']}")

    portada, fichas = rl.partir(pieza.get("texto_con_arrobas") or pieza["texto"], "dato")
    if len(fichas) < 3:
        raise RuntimeError(f"Solo {len(fichas)} fichas.")
    for f in fichas:
        f["formato"] = "dato"
    log(f"{len(fichas)} fichas")

    import banco
    rutas_banco, _ = banco.coger(2, pieza.get("etiqueta"))
    if not rutas_banco:
        raise RuntimeError("El banco no dio fotos para la portada y el cierre.")

    creditos = []
    fotos = [None] * len(fichas)
    terminos = pieza.get("fotos_busqueda") or []
    if terminos and (os.environ.get("SIN_RED") or "").lower() not in ("si", "sí", "1", "true"):
        import lugares
        try:
            encontradas, creditos = lugares.conseguir(terminos[:len(fichas)])
            for i, r in enumerate(encontradas):
                if i < len(fotos):
                    fotos[i] = r
        except Exception as e:  # noqa: BLE001
            log(f"Commons falló ({e})")
    puestas = sum(1 for f in fotos if f)
    log(f"{puestas} de {len(fichas)} fichas con foto propia")
    for i in range(len(fotos)):
        if not fotos[i]:
            fotos[i] = rutas_banco[i % len(rutas_banco)]

    TRABAJO.mkdir(parents=True, exist_ok=True)
    for v in TRABAJO.glob("*"):
        v.unlink()

    titulo = pieza.get("gancho_tiktok") or portada
    pie = pieza.get("pie_tiktok") or "Quédate que son buenos"
    cierre_txt = "¿Cuál no sabías?"

    try:
        wav = TRABAJO / "voz.wav"
        duraciones = rl.narrar_fichas(titulo, fichas, cierre_txt, wav, "dato")
        log("  " + " · ".join(f"{d:.1f}s" for d in duraciones))

        trozos_clips = []

        # LA PORTADA ENSEÑA EL PRIMER DATO, no la cara de Allie.
        #
        # El gancho dice «el gazpacho original no llevaba tomate» y se veía
        # un primer plano de una señora. El primer segundo es el que decide
        # si alguien se queda, y una frase que nombra una cosa mientras se
        # enseña otra desperdicia justo ese segundo. Allie se queda para el
        # cierre, que es donde se pide el comentario y donde tiene sentido
        # que aparezca quien lo pide.
        fondo = TRABAJO / "f00.jpg"
        foto_plena(fotos[0] or rutas_banco[0]).save(fondo, "JPEG", quality=92)
        tr = trozos(rl.sin_emoji(titulo), 3)
        tiempos = reparto(duraciones[0], len(tr))
        capas = []
        acum = 0
        for i, t in enumerate(tr):
            acum += len(t.split())
            png = TRABAJO / f"p00_{i}.png"
            pintar_cartel(titulo, pie, png, visible=acum)
            capas.append((png, tiempos[i]))
        c = TRABAJO / "c00.mp4"
        plano(fondo, capas, duraciones[0], c, acerca=True)
        trozos_clips.append(c)

        # fichas
        for i, ficha in enumerate(fichas):
            fondo = TRABAJO / f"f{i+1:02d}.jpg"
            foto_plena(fotos[i]).save(fondo, "JPEG", quality=92)
            tr = trozos(rl.sin_emoji(ficha["nombre"]), 3)
            tiempos = reparto(duraciones[i + 1], len(tr) + 1)
            capas, acum = [], 0
            for k, t in enumerate(tr):
                acum += len(t.split())
                png = TRABAJO / f"p{i+1:02d}_{k}.png"
                pintar(None, ficha, len(fichas), acum, False, png)
                capas.append((png, tiempos[k]))
            png = TRABAJO / f"p{i+1:02d}_d.png"
            pintar(None, ficha, len(fichas), 999, True, png)
            capas.append((png, tiempos[-1]))
            c = TRABAJO / f"c{i+1:02d}.mp4"
            plano(fondo, capas, duraciones[i + 1], c, acerca=(i % 2 == 0))
            trozos_clips.append(c)

        # cierre
        fondo = TRABAJO / "f99.jpg"
        foto_plena(rutas_banco[-1]).save(fondo, "JPEG", quality=92)
        png = TRABAJO / "p99.png"
        pintar_cartel(cierre_txt, "Dímela en comentarios", png)
        c = TRABAJO / "c99.mp4"
        plano(fondo, [(png, 0.1)], duraciones[-1], c, acerca=False)
        trozos_clips.append(c)

        lista = TRABAJO / "lista.txt"
        lista.write_text("".join(f"file '{t.name}'\n" for t in trozos_clips),
                         encoding="utf-8")
        mudo = TRABAJO / "mudo.mp4"
        rl.ff("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(mudo))

        total = sum(duraciones)
        import musica
        base_wav = TRABAJO / "base.wav"
        musica.escribir(base_wav, total + 0.4)
        log(f"Base musical de {total + 0.4:.1f}s")

        SALIDA.mkdir(exist_ok=True)
        final = SALIDA / f"dato_{datetime.now(timezone.utc):%Y%m%d_%H%M}.mp4"
        # La voz a -16 (el estándar de las redes) y la base diez decibelios
        # por debajo. Más alta se come las consonantes y el dato deja de
        # entenderse, que es lo contrario de lo que se busca.
        rl.ff("-i", str(mudo), "-i", str(wav), "-i", str(base_wav),
              "-filter_complex",
              "[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[v];"
              "[2:a]volume=-10dB[m];"
              "[v][m]amix=inputs=2:duration=first:dropout_transition=0:"
              # Un limitador al final. Sin él los picos llegaban a -0,6 dB:
              # la voz sale a -1,5 de techo y la música, al sumarse, se come
              # ese margen. No es saturación todavía, pero está a medio
              # decibelio, y las redes vuelven a procesar el audio al
              # subirlo. Un decibelio de margen cuesta nada.
              "weights=1 1:normalize=0,alimiter=limit=0.89:level=disabled[a]",
              "-map", "0:v", "-map", "[a]", "-c:v", "copy",
              "-c:a", "aac", "-b:a", "160k", "-shortest",
              "-movflags", "+faststart", str(final))

        dur = float(rl.subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(final)], capture_output=True,
            text=True).stdout.strip() or 0)
        log(f"LISTO · {final.name} · {dur:.1f}s · {final.stat().st_size/1e6:.1f} MB")
        (BASE / "video" / "ultimo-dato.json").write_text(json.dumps(
            {"archivo": final.name, "pieza": pieza["id"], "duracion": dur,
             "duraciones": [round(x, 3) for x in duraciones],
             "creditos": creditos}, ensure_ascii=False, indent=1), encoding="utf-8")
        return final
    finally:
        if seco:
            banco.devolver(rutas_banco)
            log("EN_SECO: fotos devueltas al banco.")


if __name__ == "__main__":
    main()
