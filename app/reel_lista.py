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
def partir(texto, formato="lista"):
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
        # EN EL FORMATO «DATO» NO HAY CALLE NI HORARIO: hay un titular y un
        # detalle, y el detalle es todo lo que viene después del punto medio.
        # Partirlo por frases dejaba «La Casa de Campo tiene 1» y se perdía
        # el resto del dato.
        if formato == "dato":
            fichas.append({"n": m.group(1), "nombre": nombre, "arroba": arroba,
                           "calle": resto, "horario": ""})
            continue

        # La calle es la primera frase. El horario se busca SOLO en lo que
        # viene después: «La Central de Callao · Postigo de San Martín 9.»
        # tiene una calle que empieza por «de» y lleva número, y buscando en
        # todo el texto el horario salía «de San Martín 9».
        #
        # El punto de los millares NO separa frases: «1.722 hectáreas» se
        # partía en «1» y «722 hectáreas».
        frases = [x.strip() for x in re.split(r"\.(?!\d)", resto) if x.strip()]
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


def fondo_con_foto(ruta, velo=True):
    """La foto arriba, sobre una copia de sí misma desenfocada que rellena.

    velo=False deja el fondo LIMPIO, sin el degradado oscuro de abajo. Es lo
    que hace falta cuando el fondo se va a mover: el velo tiene que quedarse
    quieto con el texto, porque si viaja con el zoom su borde sube y baja y
    se nota muchísimo más que el propio movimiento de la foto.
    """
    src = Image.open(ruta).convert("RGB")
    s = max(W / src.width, H / src.height) * 1.1
    fondo = src.resize((int(src.width * s), int(src.height * s)), Image.LANCZOS)
    fondo = fondo.filter(ImageFilter.GaussianBlur(44))
    x, y = (fondo.width - W) // 2, (fondo.height - H) // 2
    fondo = fondo.crop((x, y, x + W, y + H))

    # LA FOTO LLENA SU HUECO, de arriba del todo hasta donde empieza el
    # texto. Antes se ajustaba al ancho y se pegaba tal cual: con una foto
    # apaisada —y las de los sitios lo son casi todas— sobraban trescientos
    # píxeles por abajo que se quedaban en fondo desenfocado. Una franja
    # muerta entre la foto y el texto, y una tira borrosa arriba del todo.
    #
    # Se recorta centrado para llenar. Se pierde parte de los lados, sí,
    # pero el plano se mueve un 16 % con desplazamiento: lo que se recorta
    # acaba entrando en campo mientras el plano avanza.
    alto_hueco = FOTO_Y + FOTO_ALTO
    e = max(W / src.width, alto_hueco / src.height)
    gr = src.resize((max(W, int(src.width * e)), max(alto_hueco, int(src.height * e))),
                    Image.LANCZOS)
    cx, cy = (gr.width - W) // 2, (gr.height - alto_hueco) // 2
    fondo.paste(gr.crop((cx, cy, cx + W, cy + alto_hueco)), (0, 0))
    if not velo:
        return fondo.convert("RGB")
    return Image.alpha_composite(fondo.convert("RGBA"), velo_capa()).convert("RGB")


def velo_capa():
    """El degradado oscuro de abajo, en su propia capa transparente.

    Vive aparte del fondo porque el fondo se mueve y esto no.

    Y YA NO ES NEGRO PLANO. Estaba a 215 de opacidad sobre un desenfoque,
    que a efectos prácticos es negro: un tercio de la pantalla apagado. A
    185 se ve el color de la propia foto detrás del texto y el cuadro deja
    de parecer dos piezas pegadas. El texto se sigue leyendo, y eso está
    medido con el contraste, no mirado a ojo.
    """
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dv = ImageDraw.Draw(capa)
    inicio, largo = FOTO_Y + FOTO_ALTO - 300, 300
    for i in range(largo):
        a = int(185 * (i / largo) ** 0.75)
        dv.rectangle([0, inicio + i, W, inicio + i + 1], fill=(10, 10, 12, a))
    dv.rectangle([0, inicio + largo, W, H], fill=(10, 10, 12, 185))
    return capa


def guardar_capas(fondo, capa, destino):
    """El fondo que se moverá, en jpg; el texto quieto, en png con alfa."""
    fondo.save(destino, "JPEG", quality=93)
    capa.save(destino.with_suffix(".png"))


def pintar_ficha(ruta_foto, ficha, total, destino):
    fondo = fondo_con_foto(ruta_foto, velo=False)
    im = velo_capa()
    d = ImageDraw.Draw(im)
    margen, ancho = 70, W - 70 - MARGEN_DER
    y = TEXTO_Y

    d.text((margen, y - 70), f"{ficha['n']} de {total}",
           font=ImageFont.truetype(NEGRITA, 34), fill=ACENTO)

    if ficha.get("formato") == "dato":
        # Un titular de nueve palabras no cabe en una línea, y encogerlo
        # hasta que quepa lo deja ilegible: a 78 píxeles «El restaurante más
        # antiguo del mundo está aquí» bajaba a cuerpo 24. Aquí se envuelve.
        f_nom = ImageFont.truetype(NEGRITA, 62)
        lineas = envolver(d, sin_emoji(ficha["nombre"]), f_nom, ancho)
        while len(lineas) > 3 and f_nom.size > 42:
            f_nom = ImageFont.truetype(NEGRITA, f_nom.size - 4)
            lineas = envolver(d, sin_emoji(ficha["nombre"]), f_nom, ancho)
        for ln in lineas:
            d.text((margen, y), ln, font=f_nom, fill=CLARO)
            y += f_nom.size + 8
        y += 14
    else:
        f_nom = encajar(d, sin_emoji(ficha["nombre"]), NEGRITA, 78, ancho)
        d.text((margen, y), sin_emoji(ficha["nombre"]), font=f_nom, fill=CLARO)
        y += f_nom.size + 22

    if ficha["calle"]:
        f_c = ImageFont.truetype(NORMAL, 42)
        tope = 3 if ficha.get("formato") == "dato" else 2
        for ln in envolver(d, sin_emoji(ficha["calle"]), f_c, ancho)[:tope]:
            d.text((margen, y), ln, font=f_c, fill=CLARO)
            y += 52

    if ficha["horario"] and y < SUELO - 60:
        f_h = ImageFont.truetype(NORMAL, 38)
        for ln in envolver(d, sin_emoji(ficha["horario"]), f_h, ancho)[:2]:
            if y > SUELO - 50:
                break
            d.text((margen, y), ln, font=f_h, fill=APAGADO)
            y += 46

    guardar_capas(fondo, im, destino)


def pintar_cartel(ruta_foto, titulo, pie, destino):
    titulo, pie = sin_emoji(titulo), sin_emoji(pie or "")
    fondo = fondo_con_foto(ruta_foto, velo=False)
    im = velo_capa()
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
    guardar_capas(fondo, im, destino)


# ──────────────────────────────────────────────── voz
# VOZ=ef_dora pone narración en español. Kokoro la trae gratis y corre en la
# misma máquina, pero su propia documentación avisa de que el español «puede
# ser flojo por falta de datos de entrenamiento», así que esto es opcional y
# se decide escuchándolo, no leyendo el código.
#
# LO QUE SE LEE EN ALTO NO ES LO QUE PONE EN PANTALLA. El horario «de 11:00 a
# 14:30» en pantalla se entiende de un vistazo; dicho en alto por una máquina
# que no sabe leer relojes, suena a cualquier cosa. Así que la voz dice el
# nombre y la calle, y los horarios se quedan para los ojos.
VOZ = (os.environ.get("VOZ") or "").strip()
PAUSA = 0.45

# MÁS DULCE NO ES OTRA VOZ: Kokoro solo tiene una femenina en español,
# ef_dora. Lo que sí se puede es cambiar cómo suena esa:
#
#   VOZ_RITMO   por debajo de 1 habla más despacio. Una voz que corre suena
#               a locutora de megafonía; una que respira, no.
#   VOZ_TONO    por encima de 1 sube el tono. Se hace con asetrate, que
#               también acelera, y se compensa la velocidad con atempo, así
#               que la duración no cambia y los tiempos de los planos —que
#               se calculan antes— siguen valiendo.
#
# Pasarse de 1,10 en el tono suena a dibujo animado. 1,05-1,07 es el punto.
# MOTOR=piper usa Piper en vez de Kokoro. Cuatro veces más rápido en
# procesador normal y el modelo ocupa 61 MB en vez de 341.
#
# MOTOR=chatterbox usa Chatterbox Multilingual V3 (Resemble AI). MIT,
# gratis, 500M parámetros. En evaluaciones ciegas lo prefirieron sobre
# ElevenLabs el 63,75 % de las veces. Español nativo (language_id="es").
# Puede correr en CPU: en Actions (4 vCPU, 16GB) tarda unos 2-3 min para
# un vídeo de 30s. Se instala con «pip install chatterbox-tts».
#   pip install chatterbox-tts  (trae torch como dependencia)
#
# MOTOR=edge usa Edge TTS: las voces neuronales de Microsoft, gratis, sin
# API key, sin GPU. Reserva por si Chatterbox falla.
#   es-ES-ElviraNeural   voz femenina de España.
#   es-MX-DaliaNeural    voz femenina de México.
# Se instala con «pip install edge-tts» y corre en CPU.
#
# OJO CON LAS LICENCIAS de Piper, que aquí es lo que decide. Las voces
# españolas que mejor suenan —davefx, sharvard, ald, daniela— están
# afinadas sobre la voz «Lessac», cuyas grabaciones originales son de uso
# NO comercial. Quedan limpias:
#   es_MX-claude-high   la mejor puntuada (85/100), pero acento mexicano.
#   es_ES-mls_9972-low  española de España, 75,8, calidad «low».
#
# Se decide escuchando, no leyendo esta nota.
MOTOR = (os.environ.get("MOTOR") or "chatterbox").strip().lower()
EDGE_VOZ = os.environ.get("EDGE_VOZ") or "es-ES-ElviraNeural"
CHATTERBOX_LANG = os.environ.get("CHATTERBOX_LANG") or "es"
PIPER_MODELO = os.environ.get("PIPER_MODELO") or "/tmp/piper/voz.onnx"

VOZ_RITMO = float(os.environ.get("VOZ_RITMO") or 1.0)
VOZ_TONO = float(os.environ.get("VOZ_TONO") or 1.0)


def decir(pipeline, texto):
    import numpy as np
    trozos = [a for _, _, a in pipeline(texto, voice=VOZ, speed=VOZ_RITMO)]
    if not trozos:
        raise RuntimeError(f"Kokoro no devolvió audio para: {texto[:50]}")
    return np.concatenate(trozos)


def decir_piper(texto, destino):
    """Piper por línea de órdenes: más estable entre versiones que su API."""
    r = subprocess.run(
        ["piper", "--model", PIPER_MODELO, "--output_file", str(destino),
         "--length-scale", f"{1 / VOZ_RITMO:.3f}"],
        input=texto, capture_output=True, text=True)
    if r.returncode or not destino.exists():
        raise RuntimeError(f"Piper falló ({r.returncode}): {r.stderr[-300:]}")
    import soundfile as sf
    audio, frec = sf.read(str(destino), dtype="float32")
    return audio, frec


VOZ_REF = os.environ.get("VOZ_REF") or ""


def referencia_femenina(cache={}):
    """Un clip corto de voz FEMENINA de ESPAÑA para que Chatterbox lo clone.

    POR QUÉ. Teresa: «es una voz de hombre cuando es una mujer, no es
    castellano». Chatterbox sin referencia saca una voz masculina y un
    español neutro/latino. Chatterbox NO tiene parámetro de género ni de
    acento: lo único que controla el timbre es un audio de referencia
    (audio_prompt_path). Así que se le da uno.

    De dónde sale la referencia, siendo todo gratis: la genera Edge TTS con
    ElviraNeural (femenina, es-ES) una sola vez. OJO: el resultado final NO
    suena a Elvira. Elvira solo presta el timbre y el acento; la frase de
    verdad la sintetiza Chatterbox con su prosodia expresiva. Es decir,
    cogemos de Edge lo único que estaba bien (mujer, castellana) y lo
    decimos con el motor que suena a persona.

    Se puede forzar otra referencia con la variable VOZ_REF (ruta a un wav).
    """
    global VOZ_REF
    if VOZ_REF and Path(VOZ_REF).exists():
        return VOZ_REF
    if "ruta" in cache:
        return cache["ruta"]
    ref = Path("/tmp/ref_femenina_es.wav")
    if not ref.exists():
        import asyncio
        import edge_tts
        # Rico en castellano: ceceo, «vosotros», entonación de España.
        guion = ("Hola, ¿qué tal? Soy española, de Madrid. Os voy a contar "
                 "un par de cosas que seguro que no sabíais. Prestad atención, "
                 "que esto os interesa.")
        mp3 = ref.with_suffix(".mp3")
        async def _g():
            await edge_tts.Communicate(guion, "es-ES-ElviraNeural").save(str(mp3))
        asyncio.run(_g())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
                        "-ar", "24000", "-ac", "1", str(ref)], check=True)
        mp3.unlink(missing_ok=True)
        log("Referencia femenina castellana generada (Edge→clip)")
    cache["ruta"] = str(ref)
    return str(ref)


def decir_chatterbox(texto, destino, model_cache={}):
    """Chatterbox Multilingual V3 clonando una voz femenina castellana.

    POR QUÉ CHATTERBOX Y NO EDGE A SECAS. Edge es la voz de lectura de
    Microsoft: funcional pero plana, se nota la máquina (Teresa: «esa voz
    fea»). Chatterbox suena conversacional de verdad —en evaluaciones
    ciegas lo prefirieron sobre ElevenLabs el 63,75 %— pero por defecto
    saca voz de hombre. La solución: que Chatterbox CLONE un timbre
    femenino de España (ver referencia_femenina) en vez de inventarse uno.

    El modelo pesa ~2GB. En CPU (4 vCPU de Actions) tarda 1-2 min para 30s
    de voz y cabe en los 16GB de RAM. Se cachea entre llamadas.
    """
    import numpy as np

    if "model" not in model_cache:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        log("Cargando Chatterbox Multilingual V3 (puede tardar 1-2 min)...")
        model_cache["model"] = ChatterboxMultilingualTTS.from_pretrained(
            device="cpu", t3_model="v3"
        )
        log("Chatterbox cargado")

    model = model_cache["model"]
    ref = referencia_femenina()
    wav_tensor = model.generate(
        texto, language_id=CHATTERBOX_LANG, audio_prompt_path=ref)

    # wav_tensor es un tensor torch [1, N] o [N]. Convertir a numpy float32.
    audio = wav_tensor.squeeze().cpu().numpy().astype(np.float32)
    # Normalizar a [-1, 1] si no lo está
    peak = np.abs(audio).max()
    if peak > 1.0:
        audio = audio / peak
    frec = model.sr  # frecuencia de muestreo del modelo

    # Aplicar ritmo si se pidió
    if abs(VOZ_RITMO - 1.0) > 0.01:
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp_wav = destino.with_suffix(".raw.wav")
        _escribir_wav(tmp_wav, audio, frec)
        out_wav = destino.with_suffix(".wav")
        factor = f"{1 / VOZ_RITMO:.4f}"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-i", str(tmp_wav), "-af", f"atempo={factor}",
                        str(out_wav)], check=True)
        import wave
        with wave.open(str(out_wav), "r") as w:
            frames = w.readframes(w.getnframes())
            audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32767
        frec_out = frec  # atempo no cambia la frecuencia
        tmp_wav.unlink(missing_ok=True)
        return audio, frec_out

    # Resamplear a 24kHz para ser compatible con el resto del pipeline
    if frec != 24000:
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp_wav = destino.with_suffix(".orig.wav")
        _escribir_wav(tmp_wav, audio, frec)
        out_wav = destino.with_suffix(".wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-i", str(tmp_wav), "-ar", "24000", "-ac", "1",
                        str(out_wav)], check=True)
        import wave
        with wave.open(str(out_wav), "r") as w:
            frames = w.readframes(w.getnframes())
            audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32767
        frec = 24000
        tmp_wav.unlink(missing_ok=True)

    return audio, frec


def decir_edge(texto, destino):
    """Edge TTS: voces neuronales de Microsoft, gratis y naturales.

    POR QUÉ EDGE Y NO PIPER. Teresa: «la voz de la chica me parece
    superartificial». Piper es_MX-claude-high está entrenada con pocas
    horas de grabación de voluntarios; las voces Neural de Microsoft
    están entrenadas con órdenes de magnitud más de datos y suenan como
    una persona de verdad. No necesitan GPU, API key, ni modelo local.

    La velocidad se controla con el parámetro rate: «+20%» habla más
    rápido, «-10%» más despacio. El ritmo por defecto de ElviraNeural
    ya es conversacional, así que solo se toca si VOZ_RITMO difiere de 1.
    """
    import asyncio
    import edge_tts
    rate = ""
    if abs(VOZ_RITMO - 1.0) > 0.01:
        pct = int((VOZ_RITMO - 1.0) * 100)
        rate = f"{pct:+d}%"
    async def _gen():
        com = edge_tts.Communicate(texto, EDGE_VOZ, rate=rate or "+0%")
        await com.save(str(destino))
    asyncio.run(_gen())
    if not destino.exists() or destino.stat().st_size < 100:
        raise RuntimeError(f"Edge TTS no generó audio para: {texto[:50]}")
    # Edge TTS genera mp3; convertir a wav para el pipeline
    wav = destino.with_suffix(".wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-i", str(destino), "-ar", "24000", "-ac", "1",
                    str(wav)], check=True)
    import numpy as np
    import wave
    with wave.open(str(wav), "r") as w:
        frames = w.readframes(w.getnframes())
        audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32767
    frec = 24000
    return audio, frec


def _escribir_wav(destino, audio, frec):
    """Escribir wav con stdlib, sin depender de soundfile."""
    import wave as wv
    import numpy as np
    destino.parent.mkdir(parents=True, exist_ok=True)
    with wv.open(str(destino), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frec)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def narrar_fichas(portada, fichas, cierre, destino_wav, formato="lista"):
    """Devuelve la duración que tiene que durar cada plano, por su audio."""
    import numpy as np
    try:
        import soundfile as sf
    except ImportError:
        sf = None

    # EN EL FORMATO «DATO», LA VOZ LEE SOLO EL TITULAR.
    #
    # Leyendo también el detalle, cada ficha se iba a once segundos y el
    # vídeo entero a 58,9. Una pantalla quieta diez segundos es lo que peor
    # funciona: cambiar de plano cada cuatro da un 58 % de retención frente
    # al 41 % de un vídeo estático.
    #
    # Es el mismo principio que ya se aplicaba a los horarios: lo que se lee
    # en alto no tiene por qué ser lo que pone en pantalla. La voz lleva el
    # ritmo, el texto lleva los datos.
    if formato == "dato":
        # La voz dice el campo «dicho» si la pieza lo trae (una frase larga y
        # conversacional), y si no, el titular corto de pantalla.
        dichas = [x.get("dicho") or x["nombre"] for x in fichas]
    else:
        dichas = [f"{x['nombre']}. {x['calle']}." for x in fichas]
    frases = [portada] + dichas + [cierre]
    frec = 24000
    if MOTOR == "chatterbox":
        log(f"Motor: Chatterbox Multilingual · {CHATTERBOX_LANG}")
        pipeline = None
    elif MOTOR == "edge":
        log(f"Motor: Edge TTS · {EDGE_VOZ}")
        pipeline = None
    elif MOTOR == "piper":
        log(f"Motor: Piper · {Path(PIPER_MODELO).name}")
        pipeline = None
    else:
        from kokoro import KPipeline
        pipeline = KPipeline(lang_code="e")      # español
        log(f"Motor: Kokoro · {VOZ}")

    pistas, duraciones = [], []
    for i, frase in enumerate(frases):
        if MOTOR == "chatterbox":
            a, frec = decir_chatterbox(frase, destino_wav.parent / f"p{i}.wav")
        elif MOTOR == "edge":
            a, frec = decir_edge(frase, destino_wav.parent / f"p{i}.mp3")
        elif MOTOR == "piper":
            a, frec = decir_piper(frase, destino_wav.parent / f"p{i}.wav")
        else:
            a = decir(pipeline, frase)
        d = len(a) / frec
        # El plano dura lo que la voz más un respiro, y nunca menos de 3,2s:
        # una ficha que se va antes de poder leer la calle no sirve de nada.
        duraciones.append(max(d + PAUSA, 3.2))
        hueco = np.zeros(int(frec * (duraciones[-1] - d)), dtype="float32")
        pistas.append(np.concatenate([a, hueco]))
    destino_wav.parent.mkdir(parents=True, exist_ok=True)
    todo = np.concatenate(pistas)
    if sf:
        sf.write(str(destino_wav), todo, frec)
    else:
        _escribir_wav(destino_wav, todo, frec)
    if abs(VOZ_TONO - 1.0) > 0.001:
        crudo = destino_wav.with_name("voz-cruda.wav")
        destino_wav.replace(crudo)
        ff("-i", str(crudo),
           "-af", f"asetrate={frec}*{VOZ_TONO},aresample={frec},atempo={1/VOZ_TONO:.6f}",
           str(destino_wav))
        log(f"Tono subido un {(VOZ_TONO - 1) * 100:.0f} %")
    return duraciones


# ──────────────────────────────────────────────── montar
def clip(imagen, dur, destino, acerca=True):
    """Un plano: el fondo se mueve, el texto se queda quieto encima.

    POR QUÉ EN DOS CAPAS. Antes esto aplicaba el zoom a la imagen ya
    terminada, texto incluido. Eso ponía un techo al movimiento: con un 5 %
    no se nota nada —y no se notaba: el vídeo del 23 de octubre parecía una
    foto congelada—, pero subirlo a algo visible arrastraba también las
    letras, y en TikTok el texto está a seis píxeles de la columna de
    botones. Moviendo solo el fondo, el recorrido puede ser del 16 % sin
    que una sola letra se mueva de su sitio.

    Y VA Y VIENE. Planos alternos acercan y alejan, y además desplazan en
    sentidos contrarios. Dos tomas seguidas con el mismo movimiento se leen
    como una sola toma larga, que es justo lo que había que quitar.
    """
    fot = max(2, int(dur * FPS))
    R = 0.16
    if acerca:
        z, dx = f"1.0+{R}*on/{fot}", f"(iw-iw/zoom)*(0.35+0.30*on/{fot})"
    else:
        z, dx = f"{1+R}-{R}*on/{fot}", f"(iw-iw/zoom)*(0.65-0.30*on/{fot})"
    mov = (f"scale={W*2}:-1,zoompan=z='{z}':d={fot}:x='{dx}':"
           f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}")
    capa = Path(imagen).with_suffix(".png")
    if capa.exists():
        ff("-loop", "1", "-i", str(imagen), "-loop", "1", "-i", str(capa),
           "-t", f"{dur:.3f}", "-filter_complex",
           f"[0:v]{mov}[bg];[bg][1:v]overlay=0:0,format=yuv420p,setsar=1",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-r", str(FPS), str(destino))
        return
    ff("-loop", "1", "-i", str(imagen), "-t", f"{dur:.3f}",
       "-vf", f"{mov},format=yuv420p,setsar=1",
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
    formato = pieza.get("formato", "lista")
    portada, fichas = partir(texto, formato)
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

    # FOTOS REALES DE CADA SITIO, cuando la pieza dice dónde buscarlas.
    #
    # El primer vídeo del formato «dato» hablaba del templo de Debod, de
    # Botín y del metro de Chamberí enseñando siempre la misma calle de
    # tapas con Allie delante. Un «¿sabías que…?» tiene que ENSEÑAR la cosa:
    # si la imagen no dice nada de lo que se cuenta, no hay motivo para
    # mirarla veinticuatro segundos.
    #
    # Allie se queda en la portada y en el cierre —es su cuenta, y es quien
    # presenta—; las fichas son del sitio. Y las fotos de sitios reales no
    # se generan: un Debod inventado convierte el dato en mentira.
    #
    # Si Commons no da una foto libre para un sitio, ese hueco se queda con
    # la foto del banco. Mejor Allie que una foto cuya licencia no conozco.
    creditos = []
    terminos = pieza.get("fotos_busqueda") or []
    if terminos and (os.environ.get("SIN_RED") or "").strip().lower() not in (
            "si", "sí", "true", "1"):
        import lugares
        log(f"Buscando fotos libres de {len(terminos)} sitios en Commons…")
        try:
            encontradas, creditos = lugares.conseguir(terminos[:len(fichas)])
        except Exception as e:  # noqa: BLE001
            log(f"Commons no dio nada ({e}); sigo con las fotos del banco")
            encontradas = []
        puestas = 0
        for i, r in enumerate(encontradas):
            if r and i + 1 < len(rutas):
                rutas[i + 1] = r
                puestas += 1
        log(f"{puestas} de {len(terminos)} fichas llevan foto del sitio")

    try:
        TRABAJO.mkdir(parents=True, exist_ok=True)
        trozos = []

        # El cierre depende del formato: «¿cuál es la tuya?» tiene sentido
        # tras una lista de sitios y ninguno tras cinco datos históricos.
        cierre_txt = ("¿Cuál no sabías?" if pieza.get("formato") == "dato"
                      else "¿Cuál es la tuya?")
        # El título se resuelve aquí y no más abajo: la narración lo necesita
        # para leer la portada, y definirlo después reventaba la rama con voz
        # —la única que no se puede probar en local, porque Kokoro solo está
        # en la máquina de GitHub.
        if PLATAFORMA == "tiktok":
            titulo = pieza.get("gancho_tiktok") or portada
            pie_portada = pieza.get("pie_tiktok") or "Guárdalo antes de que se te olvide"
        else:
            titulo, pie_portada = portada, "Desliza… o mejor guárdalo"

        if VOZ:
            log(f"Narrando en español con {VOZ}…")
            wav = TRABAJO / "voz.wav"
            duraciones = narrar_fichas(titulo if PLATAFORMA == "tiktok" else portada,
                                       fichas, cierre_txt, wav, formato)
            log("  " + " · ".join(f"{d:.1f}s" for d in duraciones))
        else:
            wav = None
            duraciones = [DUR_PORTADA] + [DUR_FICHA] * len(fichas) + [DUR_CIERRE]

        portada_img = TRABAJO / "00.jpg"
        pintar_cartel(rutas[0], titulo, pie_portada, portada_img)
        c = TRABAJO / "c00.mp4"
        clip(portada_img, duraciones[0], c)
        trozos.append(c)

        for i, ficha in enumerate(fichas):
            img = TRABAJO / f"{i+1:02d}.jpg"
            ficha["formato"] = formato
            pintar_ficha(rutas[i + 1], ficha, len(fichas), img)
            c = TRABAJO / f"c{i+1:02d}.mp4"
            clip(img, duraciones[i + 1], c, acerca=(i % 2 == 0))
            trozos.append(c)

        cierre_img = TRABAJO / "99.jpg"
        pintar_cartel(rutas[-1], cierre_txt, "Dímela en comentarios", cierre_img)
        c = TRABAJO / "c99.mp4"
        clip(cierre_img, duraciones[-1], c, acerca=False)
        trozos.append(c)

        lista = TRABAJO / "lista.txt"
        lista.write_text("".join(f"file '{t.name}'\n" for t in trozos), encoding="utf-8")
        mudo = TRABAJO / "mudo.mp4"
        ff("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(mudo))

        SALIDA.mkdir(exist_ok=True)
        final = SALIDA / f"reel_{datetime.now(timezone.utc):%Y%m%d_%H%M}.mp4"
        if wav and wav.exists():
            # loudnorm NO ES UN ADORNO. Piper saca la voz con picos a 0,0 dB
            # —medido el 22 de octubre: media -15,3, máximo -0,0— y eso es
            # saturación grabada en el fichero, que ya no se quita después.
            # Kokoro sale mucho más bajo, a -27 de media. Sin igualarlas, el
            # mismo vídeo suena a dos volúmenes distintos según el motor.
            #
            # I=-16 y TP=-1,5 es el estándar de audio para web: deja un
            # margen de seguridad antes del techo y es lo que esperan las
            # redes, que de todas formas vuelven a normalizar al subirlo.
            ff("-i", str(mudo), "-i", str(wav), "-c:v", "copy",
               "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
               "-c:a", "aac", "-b:a", "128k", "-shortest",
               "-movflags", "+faststart", str(final))
        else:
            # Instagram rechaza un vídeo sin pista de audio.
            ff("-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
               "-i", str(mudo), "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
               "-shortest", "-movflags", "+faststart", str(final))

        dur = sum(duraciones)
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
