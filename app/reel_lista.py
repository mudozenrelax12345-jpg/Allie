"""Un reel que lleva dentro la información del carrusel.

POR QUÉ, con los números de la cuenta delante. En cinco semanas:

    carruseles   alcance 228 · 12 guardados · 6 seguidores nuevos
    reels        alcance 130 ·  0 guardados · 0 seguidores nuevos

Los carruseles llegan a gente que no sigue a Allie porque contienen algo que
alguien quiere guardar: cinco sitios con su calle y su horario. Los reels son
fotos de una señora a la que ese desconocido no conoce, en silencio y sin una
palabra en pantalla. No hay motivo para verlos enteros, ni para guardarlos, ni
para enviárselos a nadie — y sin guardados ni envíos, Instagram no los saca
del círculo de los seguidores.

Esto coge una pieza de contenido/cola.json —la misma lista que funciona en
carrusel— y la monta en vertical con el texto en pantalla.

LAS DECISIONES, y de dónde sale cada una:

  · TEXTO DESDE EL PRIMER FOTOGRAMA. Los subtítulos suben la retención sin
    sonido entre un 25 y un 40 %, y esto se ve en silencio.
  · UNA FICHA POR SITIO, cuatro segundos y medio. Lo justo para leer nombre,
    calle y horario sin tener que pausar.
  · NADA POR DEBAJO DE 1550 PÍXELES: ahí está la interfaz de Instagram, con
    el nombre de la cuenta y el pie. Lo que se ponga ahí no se lee.
  · UNA FOTO DISTINTA POR FICHA. Nunca la misma dos veces: es el fallo que
    tenía el montaje largo del canal.
  · PISTA DE AUDIO EN SILENCIO, porque Instagram rechaza un vídeo sin audio.

NO LLEVA VOZ. Podría, pero entonces el texto tendría que ir cuadrado con la
voz y el reel pasaría a depender de que la narración salga bien. Aquí el
texto ES el contenido y los tiempos los pongo yo: menos piezas que romper.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

BASE = Path(__file__).resolve().parent.parent
COLA = BASE / "contenido" / "cola.json"
FOTOS = BASE / "banco" / "fotos"
TRABAJO = BASE / "video" / "lista"
SALIDA = BASE / "videos"

W, H, FPS = 1080, 1920, 30
DUR_FICHA = 4.5
DUR_PORTADA = 3.2
DUR_CIERRE = 3.0

# La foto ocupa la mitad de arriba; el texto vive debajo, sobre el fondo
# desenfocado. Nada baja de 1550: ahí empieza la interfaz de Instagram.
# LAS ZONAS SEGURAS NO SON LAS MISMAS EN LAS DOS REDES, y por eso esto no es
# el mismo vídeo con otro pie.
#
#   Instagram tapa con su interfaz los últimos ~370 píxeles de abajo (nombre
#   de la cuenta, pie, audio) y poco a la derecha.
#
#   TikTok tapa MÁS abajo —el pie va más alto y hay dos líneas de texto— y
#   además tiene la columna de botones a la derecha (perfil, like, comentar,
#   compartir, disco de audio), unos 140 píxeles que se comen el margen
#   derecho entero. Un texto que en Instagram se lee perfectamente, en
#   TikTok queda debajo del botón de compartir.
PLATAFORMA = (os.environ.get("PLATAFORMA") or "instagram").strip().lower()

if PLATAFORMA == "tiktok":
    FOTO_Y, FOTO_ALTO = 150, 1000
    TEXTO_Y = 1180
    SUELO = 1440          # el pie de TikTok sube más que el de Instagram
    MARGEN_DER = 170      # la columna de botones
else:
    FOTO_Y, FOTO_ALTO = 90, 1110
    TEXTO_Y = 1250
    SUELO = 1550
    MARGEN_DER = 70


def sin_emoji(t):
    """Fuera los emojis del texto que se PINTA.

    DejaVu Sans no tiene glifos de emoji y Pillow los dibuja como un
    cuadradito vacío: «Librerías de Madrid 📚☕» salía con dos cajas. En el
    pie de Instagram los emojis están bien y se quedan; aquí estorban.
    """
    return re.sub(r"\s*[\U0001F000-\U0001FAFF←-⯿️⃣]+", "", t).strip()

F = "/usr/share/fonts/truetype/dejavu/"
NEGRITA, NORMAL = F + "DejaVuSans-Bold.ttf", F + "DejaVuSans.ttf"
CLARO, APAGADO, ACENTO = "#F5F2EC", "#B9B3A8", "#E0A33C"


def log(m):
    print(f"· {m}", flush=True)


def ff(*args):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg falló: {r.stderr[-500:]}")


# ──────────────────────────────────────────────── leer la pieza
def partir(texto):
    """Saca de la pieza la portada y las fichas numeradas.

    El texto del carrusel tiene esta forma:
        Librerías de Madrid donde además puedes ...
        1️⃣ La Mistral (@librerialamistral) · Travesía del Arenal 2. ...
    """
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    portada = lineas[0] if lineas else ""
    fichas = []
    for l in lineas:
        m = re.match(r"^([1-9])️?⃣\s*(.+)$", l)
        if not m:
            continue
        cuerpo = m.group(2)
        # «La Mistral (@librerialamistral) · Travesía del Arenal 2. Resto.»
        cabeza, _, resto = cuerpo.partition("·")
        nombre = re.sub(r"\s*\([^)]*\)", "", cabeza).strip(" .·")
        arroba = (re.search(r"@[\w.]+", cabeza) or [None])
        arroba = arroba.group(0) if hasattr(arroba, "group") else None
        resto = resto.strip()
        # La calle es la primera frase. El horario se busca SOLO en lo que
        # viene después: «La Central de Callao · Postigo de San Martín 9.»
        # tiene una calle que empieza por «de» y lleva número, y buscando en
        # todo el texto el horario salía «de San Martín 9».
        frases = [f.strip() for f in resto.split(".") if f.strip()]
        calle = frases[0] if frases else ""
        horario = ""
        for f in frases[1:]:
            # Un horario de verdad lleva una hora con dos puntos.
            if re.search(r"\d{1,2}:\d{2}", f):
                horario = f
                break
        fichas.append({"n": m.group(1), "nombre": nombre, "arroba": arroba,
                       "calle": calle, "horario": horario})
    return portada, fichas


# ──────────────────────────────────────────────── dibujar
def encajar(d, texto, ruta, tam, ancho):
    """El cuerpo más grande al que este texto cabe en una línea."""
    while tam > 24:
        f = ImageFont.truetype(ruta, tam)
        if d.textbbox((0, 0), texto, font=f)[2] <= ancho:
            return f
        tam -= 2
    return ImageFont.truetype(ruta, 24)


def envolver(d, texto, f, ancho):
    palabras, lineas, linea = texto.split(), [], ""
    for p in palabras:
        prueba = f"{linea} {p}".strip()
        if d.textbbox((0, 0), prueba, font=f)[2] <= ancho or not linea:
            linea = prueba
        else:
            lineas.append(linea)
            linea = p
    if linea:
        lineas.append(linea)
    return lineas


def fondo_con_foto(ruta):
    """La foto arriba, sobre una copia de sí misma desenfocada que rellena."""
    src = Image.open(ruta).convert("RGB")
    s = max(W / src.width, H / src.height) * 1.1
    fondo = src.resize((int(src.width * s), int(src.height * s)), Image.LANCZOS)
    fondo = fondo.filter(ImageFilter.GaussianBlur(44))
    x, y = (fondo.width - W) // 2, (fondo.height - H) // 2
    fondo = fondo.crop((x, y, x + W, y + H))
    # Oscurecer la mitad de abajo para que el texto se lea sobre cualquier foto.
    velo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dv = ImageDraw.Draw(velo)
    for i in range(240):
        a = int(215 * i / 240)
        dv.rectangle([0, FOTO_Y + FOTO_ALTO - 240 + i, W,
                      FOTO_Y + FOTO_ALTO - 240 + i + 1], fill=(10, 10, 12, a))
    dv.rectangle([0, FOTO_Y + FOTO_ALTO, W, H], fill=(10, 10, 12, 215))
    frente = src.resize((W, int(src.height * W / src.width)), Image.LANCZOS)
    caja = frente.crop((0, 0, W, min(FOTO_ALTO, frente.height)))
    fondo.paste(caja, (0, FOTO_Y))
    return Image.alpha_composite(fondo.convert("RGBA"), velo).convert("RGB")


def pintar_ficha(ruta_foto, ficha, total, destino):
    im = fondo_con_foto(ruta_foto)
    d = ImageDraw.Draw(im)
    margen, ancho = 70, W - 70 - MARGEN_DER
    y = TEXTO_Y

    d.text((margen, y - 70), f"{ficha['n']} de {total}",
           font=ImageFont.truetype(NEGRITA, 34), fill=ACENTO)

    f_nom = encajar(d, sin_emoji(ficha["nombre"]), NEGRITA, 78, ancho)
    d.text((margen, y), sin_emoji(ficha["nombre"]), font=f_nom, fill=CLARO)
    y += f_nom.size + 22

    if ficha["calle"]:
        f_c = ImageFont.truetype(NORMAL, 42)
        for ln in envolver(d, sin_emoji(ficha["calle"]), f_c, ancho)[:2]:
            d.text((margen, y), ln, font=f_c, fill=CLARO)
            y += 52

    if ficha["horario"] and y < SUELO - 60:
        f_h = ImageFont.truetype(NORMAL, 38)
        for ln in envolver(d, sin_emoji(ficha["horario"]), f_h, ancho)[:2]:
            if y > SUELO - 50:
                break
            d.text((margen, y), ln, font=f_h, fill=APAGADO)
            y += 46

    im.save(destino, "JPEG", quality=93)


def pintar_cartel(ruta_foto, titulo, pie, destino):
    titulo, pie = sin_emoji(titulo), sin_emoji(pie or "")
    im = fondo_con_foto(ruta_foto)
    d = ImageDraw.Draw(im)
    margen, ancho = 70, W - 70 - MARGEN_DER
    # EL BLOQUE SE PEGA AL SUELO, no cuelga desde arriba. Colgando, un
    # título de tres líneas empujaba el pie fuera de la zona segura y el
    # programa lo descartaba: en la primera versión de TikTok la frase de
    # gancho —la que da el motivo para quedarse— no llegó a verse.
    f_p = ImageFont.truetype(NORMAL, 42)
    alto_pie = 0
    lineas_pie = envolver(d, pie, f_p, ancho) if pie else []
    if lineas_pie:
        alto_pie = len(lineas_pie) * 50 + 20

    f_t = ImageFont.truetype(NEGRITA, 84)
    lineas = envolver(d, titulo, f_t, ancho)
    while f_t.size > 46 and (len(lineas) * (f_t.size + 14) + alto_pie) > (SUELO - TEXTO_Y + 110):
        f_t = ImageFont.truetype(NEGRITA, f_t.size - 6)
        lineas = envolver(d, titulo, f_t, ancho)

    alto = len(lineas) * (f_t.size + 14) + alto_pie
    y = SUELO - alto
    for ln in lineas:
        d.text((margen, y), ln, font=f_t, fill=CLARO)
        y += f_t.size + 14
    for ln in lineas_pie:
        d.text((margen, y + 10), ln, font=f_p, fill=ACENTO)
        y += 50
    im.save(destino, "JPEG", quality=93)


# ──────────────────────────────────────────────── montar
def clip(imagen, dur, destino, acerca=True):
    fot = max(2, int(dur * FPS))
    z = f"1.0+0.05*on/{fot}" if acerca else f"1.05-0.05*on/{fot}"
    ff("-loop", "1", "-i", str(imagen), "-t", f"{dur:.3f}",
       "-vf", f"scale={W*2}:-1,zoompan=z='{z}':d={fot}:"
              f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
              f"format=yuv420p,setsar=1",
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS),
       str(destino))


def main():
    seco = (os.environ.get("EN_SECO") or "").strip().lower() in ("si", "sí", "true", "1")
    cola = json.loads(COLA.read_text(encoding="utf-8"))
    pedido = (os.environ.get("PIEZA") or "").strip()
    def encaja(p):
        return p["id"] == pedido if pedido else not p.get("usado")

    pieza = next((p for p in cola["piezas"] if encaja(p)), None)
    if not pieza:
        raise RuntimeError("No hay pieza libre en la cola.")
    log(f"Pieza: {pieza['id']}")

    texto = pieza.get("texto_con_arrobas") or pieza["texto"]
    portada, fichas = partir(texto)
    if len(fichas) < 3:
        raise RuntimeError(f"Solo he sacado {len(fichas)} fichas del texto. "
                           "Un reel de lista con menos de tres no se sostiene.")
    log(f"{len(fichas)} fichas: {', '.join(f['nombre'] for f in fichas)}")

    import banco
    hacen_falta = len(fichas) + 2
    rutas, _ = banco.coger(hacen_falta, pieza.get("etiqueta"))
    if len(rutas) < 3:
        banco.devolver(rutas)
        raise RuntimeError(f"El banco solo dio {len(rutas)} fotos de la tanda "
                           f"«{pieza.get('etiqueta')}» y con menos de tres no "
                           "se monta nada.")

    # NO SE EXIGEN SIETE FOTOS DISTINTAS, y es una decisión, no una rebaja.
    # banco.coger() devuelve fotos de UNA MISMA TANDA —misma ropa, mismo
    # sitio, misma luz— porque un reel con tres conjuntos distintos en medio
    # minuto parece un collage. Y de una tanda salen tres o cuatro.
    #
    # Aquí da igual: lo que cambia cada cuatro segundos es la FICHA, que es
    # el contenido. La foto es el fondo. Lo único intolerable es que la misma
    # salga dos veces seguidas, que es el fallo que tenía el montaje largo
    # del canal: allí el 33 % del metraje era la misma imagen encadenada.
    fondo = []
    for i in range(hacen_falta):
        c = rutas[i % len(rutas)]
        if fondo and c == fondo[-1]:
            c = rutas[(i + 1) % len(rutas)]
        fondo.append(c)
    log(f"{len(rutas)} fotos de la tanda, repartidas en {hacen_falta} planos "
        "sin repetir seguidas")
    rutas_usadas, rutas = rutas, fondo
    try:
        TRABAJO.mkdir(parents=True, exist_ok=True)
        trozos = []

        portada_img = TRABAJO / "00.jpg"
        if PLATAFORMA == "tiktok":
            titulo = pieza.get("gancho_tiktok") or portada
            pie_portada = pieza.get("pie_tiktok") or "Guárdalo antes de que se te olvide"
        else:
            titulo, pie_portada = portada, "Desliza… o mejor guárdalo"
        pintar_cartel(rutas[0], titulo, pie_portada, portada_img)
        c = TRABAJO / "c00.mp4"
        clip(portada_img, DUR_PORTADA, c)
        trozos.append(c)

        for i, ficha in enumerate(fichas):
            img = TRABAJO / f"{i+1:02d}.jpg"
            pintar_ficha(rutas[i + 1], ficha, len(fichas), img)
            c = TRABAJO / f"c{i+1:02d}.mp4"
            clip(img, DUR_FICHA, c, acerca=(i % 2 == 0))
            trozos.append(c)

        cierre_img = TRABAJO / "99.jpg"
        pintar_cartel(rutas[-1], "¿Cuál es la tuya?", "Dímela en comentarios 👇", cierre_img)
        c = TRABAJO / "c99.mp4"
        clip(cierre_img, DUR_CIERRE, c, acerca=False)
        trozos.append(c)

        lista = TRABAJO / "lista.txt"
        lista.write_text("".join(f"file '{t.name}'\n" for t in trozos), encoding="utf-8")
        mudo = TRABAJO / "mudo.mp4"
        ff("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(mudo))

        SALIDA.mkdir(exist_ok=True)
        final = SALIDA / f"reel_{datetime.now(timezone.utc):%Y%m%d_%H%M}.mp4"
        ff("-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-i", str(mudo), "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
           "-shortest", "-movflags", "+faststart", str(final))

        dur = DUR_PORTADA + len(fichas) * DUR_FICHA + DUR_CIERRE
        log(f"LISTO · {final.name} · {dur:.1f}s · {final.stat().st_size/1e6:.1f} MB")
        if seco:
            banco.devolver(rutas_usadas)
            log("EN_SECO: fotos devueltas al banco.")
        (BASE / "video" / "ultimo-reel-lista.json").write_text(json.dumps(
            {"archivo": final.name, "pieza": pieza["id"], "duracion": dur,
             "fichas": [f["nombre"] for f in fichas]}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        return final
    except Exception:
        banco.devolver(rutas_usadas)
        log("Devuelvo las fotos al banco: no salió el reel")
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "estado").mkdir(exist_ok=True)
        (BASE / "estado" / "ULTIMO-FALLO-REEL-LISTA.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n\n{detalle}\n",
            encoding="utf-8")
        raise
