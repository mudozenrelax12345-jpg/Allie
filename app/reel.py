"""Monta un reel vertical a partir de fotos de Allie generadas con Pollinations.

Se ejecuta en GitHub Actions (que sí tiene internet y ffmpeg):
1. Gemini inventa la idea, las escenas y el texto del post.
2. Pollinations crea las fotos con la cara de Allie (gratis).
3. ffmpeg las monta en vertical 1080x1920 con movimiento lento y fundidos.
4. El vídeo se sube a un alojamiento público y la dirección queda guardada
   en videos/ultimo.json, para que Claude lo programe en Metricool.
"""
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloudflare  # noqa: E402
import espacio as espacio_mod  # noqa: E402
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
VIDEOS = BASE / "videos"
TRABAJO = BASE / ".reel"
PERSONA_FILE = BASE / "personaje.yml"

N_FOTOS = 4
DUR = 3.6          # segundos por foto
FUNDIDO = 0.5
W, H = 1080, 1920


def log(m):
    print(f"· {m}", flush=True)


def persona():
    d = yaml.safe_load(PERSONA_FILE.read_text(encoding="utf-8")) or {}
    if not d.get("referencia_url"):
        raise RuntimeError("Falta 'referencia_url' en personaje.yml (la foto de Allie de referencia).")
    return d


# ------------------------------------------------------------------ guion
def guion(p):
    temas = p.get("temas_reel") or ["un día en Madrid", "rutina de mañana", "look del día",
                                    "paseo con Booby", "café y planes", "finde de descanso"]
    tema = os.environ.get("TEMA", "").strip() or random.choice(temas)
    prompt = f"""Eres el community manager de la influencer virtual {p.get('nombre', 'Allie')} en Instagram.
Su forma de ser: {p.get('personalidad', '')}
Datos suyos: {p.get('sobre_ella', '')}

Prepara un REEL de {N_FOTOS} fotos sobre el tema: "{tema}".
Las fotos van seguidas como un pequeño vídeo, así que deben contar una secuencia
coherente (misma ropa y mismo sitio, cambiando el plano y la acción).

Devuelve SOLO un JSON:
{{
 "idea": "la idea en una frase, en español",
 "escenas": [{", ".join(['"escena en inglés"'] * N_FOTOS)}],
 "texto": "texto del post en español: primera línea con gancho, 3-5 líneas, termina con una pregunta",
 "hashtags": ["#...", "..."]
}}

Reglas para las escenas: en inglés, muy descriptivas, pero SOLO del lugar, la
ropa, la pose, la luz y el encuadre. NUNCA describas cómo es ella: ni el color
del pelo, ni los ojos, ni la edad, ni «a young woman with…». El generador parte
de una foto suya, y si el texto dice de qué color es el pelo le hace caso al
texto y dibuja a otra mujer. Empieza cada escena por «The same woman, ».
MUY IMPORTANTE con el encuadre: usa planos de medio cuerpo, de cintura para arriba o primeros planos
("upper-body shot", "medium shot from the waist up", "close-up"). NADA de planos de cuerpo entero ni
de cuerpo completo: es donde la IA se inventa piernas y manos de más. Evita también manos en posturas
raras o muy en primer plano. NUNCA pongas que sujeta algo con la mano —ni taza,
ni pincel, ni móvil, ni correa, ni libro—: una mano agarrando un objeto fino
es lo que peor hace el generador y tira el reel entero. Nada de texto, logotipos ni marcas dentro de la imagen.
LA BOCA: describe siempre la expresión con la boca cerrada o con una sonrisa suave de labios
juntos. NUNCA pongas que se ríe a carcajadas, que habla, que canta, que come o que tiene la
boca abierta: es donde el generador falla y salen dientes deformes.
Contenido apto para todos los públicos.
Reglas para el texto: 4 o 5 hashtags, incluye {p.get('hashtags_base', ['#Allie', '#AIInfluencer'])}."""
    g = gemini.json_(prompt)
    escenas = (g.get("escenas") or [])[:N_FOTOS]
    while len(escenas) < N_FOTOS:
        escenas.append(escenas[-1] if escenas else tema)
    g["escenas"], g["tema"] = escenas, tema
    return g


# ------------------------------------------------------------------ fotos
# La boca es donde más se nota que una foto está generada: dientes de más,
# encías raras, labios asimétricos. Se pide expresamente que esté serena y
# cerrada, o con una sonrisa suave, que es lo que el generador hace bien.
ANATOMIA = ("anatomically correct, exactly two arms and two legs, five fingers on each hand, "
            "natural human proportions, no extra limbs, no duplicated body parts, "
            "no deformed hands or feet")

CARA = ("calm closed mouth or a soft gentle smile with lips together, well-defined natural lips, "
        "no open mouth, not laughing, not talking, no visible teeth, symmetrical face, "
        "clean jawline, clear detailed eyes looking naturally, sharp focus on the face, "
        "high detail skin texture with visible pores, professional portrait photography")


def frase(escena, p):
    return (f"The same young woman from the reference photo, identical face and hair, {escena}. "
            f"Photorealistic smartphone photo, natural skin, soft natural light, "
            f"{CARA}, {ANATOMIA}, vertical 4:5 crop, no text, no watermark")


# De dónde salen las fotos.
#
# Hasta ahora, de Pollinations con el modelo "kontext", que es el que copia la
# cara de una foto de referencia. Ese modelo pasó a ser de pago (HTTP 402,
# "insufficient balance"), y aquí no se paga: ahora las hace Gemini, que lo
# hace gratis y cuya clave ya estaba puesta para los textos.
#
# Lo que no se negocia es la foto de referencia. Sin ella el generador dibuja a
# otra mujer, y una influencer que cambia de cara cada semana no es nadie:
# antes que publicar un reel con una desconocida, no se publica.
PUERTAS = [
    ("gen · clave en cabecera",    "https://gen.pollinations.ai/image/{t}",      True),
    ("prompt · clave en cabecera", "https://image.pollinations.ai/prompt/{t}",   True),
    ("prompt · sin clave",         "https://image.pollinations.ai/prompt/{t}",   False),
]

INTENTOS = 6
# Esperas cortas a propósito. Cuando un modelo se queda sin cupo, esperar un
# minuto y medio no le devuelve el cupo: solo consume el tiempo del trabajo
# (30 minutos) y lo deja morir a medias. Mejor agotar los modelos deprisa.
ESPERAS = [5, 10, 20, 30, 40, 40]


def estado_referencia(url):
    """Si la foto de Allie ya no está en su sitio, kontext no puede copiar la cara
    y falla sin decir por qué. Conviene saberlo antes de buscar en otro lado."""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60, stream=True)
        tipo = r.headers.get("content-type", "?")
        largo = r.headers.get("content-length", "?")
        r.close()
        return f"HTTP {r.status_code}, {tipo}, {largo} bytes"
    except requests.RequestException as e:
        return f"no se pudo abrir ({type(e).__name__})"


_referencia = {}


def foto_referencia(url):
    """La foto de Allie, descargada una vez y guardada para todas las escenas."""
    if url not in _referencia:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
        r.raise_for_status()
        _referencia[url] = r.content
    return _referencia[url]


_vertical = None


def referencia_bytes(p):
    """Los bytes de la foto de referencia, para que el revisor compare caras.

    Se cachea: en una tanda de nueve fotos se pide nueve veces y es siempre la
    misma. Si no se puede traer, se devuelve None y el revisor se queda sin
    comprobar la identidad, que es peor que comprobarla pero mejor que no
    generar nada.
    """
    global _referencia_cache
    if _referencia_cache is not None:
        return _referencia_cache or None
    try:
        _referencia_cache = referencia_vertical(p["referencia_url"]).read_bytes()
    except Exception as e:  # noqa: BLE001
        log(f"No se pudo traer la referencia para comparar caras: {e}")
        _referencia_cache = b""
    return _referencia_cache or None


_referencia_cache = None


def referencia_vertical(url):
    """La foto de Allie recortada a vertical, guardada en un fichero.

    Kontext devuelve la imagen con la forma de la que se le da. La foto
    original es apaisada, y una foto apaisada dentro de un reel deja a Allie
    pequeña en medio de dos franjas borrosas. Recortada a 4:5 por arriba —que
    es donde está la cara— sale ya con la forma buena.
    """
    global _vertical
    if _vertical is None:
        TRABAJO.mkdir(exist_ok=True)
        from io import BytesIO
        im = Image.open(BytesIO(foto_referencia(url))).convert("RGB")
        alto = min(im.height, int(im.width * 5 / 4))
        ancho = int(alto * 4 / 5)
        x = (im.width - ancho) // 2
        y = min(max(0, (im.height - alto) // 3), im.height - alto)   # hacia la cara
        _vertical = TRABAJO / "referencia.jpg"
        im.crop((x, y, x + ancho, y + alto)).save(_vertical, "JPEG", quality=95)
    return _vertical


# El sitio que de verdad conserva la cara de Allie, y gratis.
#
# Gemini dejó de dar imágenes en el nivel gratuito y Pollinations puso de pago
# el único modelo suyo que copiaba una cara; lo que le queda gratis devuelve a
# otra mujer. Hugging Face tiene espacios públicos que ejecutan FLUX.1
# Kontext, que es un modelo de edición: se le da la foto de Allie y la escena,
# y devuelve a la misma persona en otro sitio. Se puede llamar sin cuenta y sin
# tarjeta, aunque va "según disponibilidad": a veces hay cola y a veces el
# espacio está reiniciándose, así que hay más de uno y se reintenta.
# Qué espacio genera las fotos, en orden de preferencia.
#
# Se sale de FLUX.1-Kontext-Dev por dos razones, y las dos las descubrí tarde:
#
# 1. LICENCIA. Su licencia define como no comercial todo uso del que se reciba
#    "pago directo o indirecto" y excluye expresamente la "actividad
#    generadora de ingresos". Las imágenes ya generadas sí se pueden usar y
#    vender —eso lo dice aparte—, pero ejecutar el modelo para una cuenta que
#    monetiza queda fuera. Qwen-Image-Edit es Apache 2.0, sin esa pega, y su
#    ficha dice que está hecho precisamente para "preservación de la identidad
#    facial" con una a tres fotos de referencia.
#
# 2. CUOTA. Hugging Face no cuenta imágenes, cuenta SEGUNDOS de GPU: cinco
#    minutos al día en la cuenta gratuita. A 28 pasos cada foto se comía más
#    de un minuto, y de ahí salían las cuatro fotos diarias que nos tenían
#    bloqueados. Las versiones rápidas trabajan a cuatro u ocho pasos.
#
# Van primero las rápidas. FLUX queda de último recurso para no quedarnos sin
# nada si los demás están caídos; si se usa, queda anotado en el registro.
ESPACIOS = [e.strip() for e in os.environ.get(
    "HF_ESPACIOS",
    "multimodalart/Qwen-Image-Edit-Fast,"
    "linoyts/Qwen-Image-Edit-2511-Fast,"
    "prithivMLmods/Qwen-Image-Edit-2509-LoRAs-Fast,"
    "Qwen/Qwen-Image-Edit-2511,"
    "Qwen/Qwen-Image-Edit,"
    "black-forest-labs/FLUX.1-Kontext-Dev").split(",") if e.strip()]

# Pasos de cálculo. Es la palanca que decide cuánta cuota gasta cada foto.
PASOS = int(float(os.environ.get("PASOS", "8") or 8))

# Cuánto tardó cada llamada, para poder ver en qué se va la cuota del día.
GASTO = []


ASPECTO = re.compile(
    r"\b(?:blonde|brunette|brown[- ]haired|dark[- ]haired|red[- ]haired|ginger|"
    r"black[- ]haired|long brown hair|brown hair|blond hair|black hair|"
    r"red hair|blue eyes|green eyes|brown eyes|hazel eyes|"
    r"(?:young |beautiful |pretty )?woman with [^,.]{0,40})\b", re.I)


def sin_aspecto(escena):
    """Quita de la escena cualquier descripción de cómo es ella.

    Kontext parte de la foto de Allie, pero si el texto le dice de qué color
    es el pelo, le hace caso al texto. De dos fotos generadas el mismo día,
    la que pedía «long brown hair» devolvió a una morena que no era ella; la
    que decía «the same young woman in the same sweater» devolvió a Allie.
    Su cara la pone la referencia; el texto solo pone el sitio.
    """
    limpia = ASPECTO.sub("the same woman", escena)
    limpia = re.sub(r"\b(?:a|an|the)\s+the same woman", "the same woman", limpia, flags=re.I)
    limpia = re.sub(r"(the same woman[,\s]+){2,}", "the same woman, ", limpia, flags=re.I)
    return re.sub(r"\s{2,}", " ", limpia).strip()


class SinCuota(RuntimeError):
    """La GPU gratuita de Hugging Face dice que no queda cuota para hoy.

    Se distingue de cualquier otro fallo porque no se arregla esperando: dio
    18 reintentos en una tanda, siete minutos, todos con el mismo mensaje.
    Quien la reciba debe parar, no insistir.
    """


def _es_cuota(texto):
    t = str(texto).lower()
    return "zerogpu" in t and ("exceeded" in t or "quota" in t or "limit" in t)


def _cliente(espacio, ficha):
    """Entra en el espacio. Con cuenta si hay ficha; el nombre del parámetro
    cambia según la versión de la librería, así que se prueban los tres."""
    from gradio_client import Client
    if ficha:
        for como in ("hf_token", "auth_token", "token"):
            try:
                return Client(espacio, verbose=False, **{como: ficha})
            except TypeError:
                continue
    return Client(espacio, verbose=False)


def kontext(escena, p):
    """Devuelve (bytes, None) o (None, lo que dijo cada espacio).

    Levanta SinCuota si todas las vías contestaron que no queda cuota.
    """
    try:
        from gradio_client import Client, handle_file  # noqa: F401
    except ImportError:
        return None, ["falta la biblioteca gradio_client"]
    from gradio_client import handle_file

    escena = sin_aspecto(escena)
    img = referencia_vertical(p["referencia_url"])
    orden = (f"Keep her face, hair, skin tone and body exactly as they are — it must be "
             f"unmistakably the same woman. Place her in this scene: {escena}. "
             f"{CARA}. {ANATOMIA}. Photorealistic smartphone photo, soft natural light. "
             f"No text, no logos and no watermark anywhere in the image.")

    dichos_cf = []

    # Cloudflare primero, cuando hay credenciales: su cupo gratuito da para
    # unas noventa fotos al día y se reinicia a las 00:00 UTC en punto, no en
    # una ventana que se va moviendo. Si no hay credenciales o falla, se sigue
    # por Hugging Face exactamente como antes.
    if cloudflare.hay():
        datos, segundos, modelo = cloudflare.generar(img.read_bytes(), orden)
        if datos:
            GASTO.append({"espacio": f"cloudflare {modelo}", "api": "ai/run",
                          "segundos": segundos, "pasos": 4})
            log(f"cloudflare · {modelo} · {segundos}s")
            return datos, None
        dichos_cf = [f"cloudflare · {m}" for m in (modelo or [])]
        for m in dichos_cf:
            log(m)

    # Con cuenta primero, porque la cuota diaria es mayor. Si se agota, se
    # reintenta sin cuenta: esa cuota va por dirección IP, y cada ejecución
    # de GitHub estrena máquina, así que es una segunda oportunidad de verdad
    # y no una repetición de lo mismo.
    ficha = os.environ.get("HF_TOKEN") or None
    vias = [("con cuenta", ficha), ("sin cuenta", None)] if ficha else [("sin cuenta", None)]

    dichos, cuotas = list(dichos_cf), 0
    for espacio in ESPACIOS:
        if cuotas:
            break      # la cuota la comparten todos: no hay nada que probar
        # Sin cuota por una vía no quiere decir sin cuota por la otra: la del
        # token va por cuenta y la anónima por dirección IP, y son dos bolsas
        # distintas. Antes se cortaba en la primera que lo dijera, así que la
        # segunda oportunidad que buscan las dos vías no llegaba a usarse
        # nunca. Sólo cuenta como «sin cuota» si lo dicen TODAS.
        cuota_en = []
        for comollama, quien in vias:
            try:
                # Cada espacio llama a sus parámetros como quiere, así que se
                # le pregunta en vez de suponer que son los de FLUX.
                ruta, segundos, api = espacio_mod.generar(
                    espacio, quien, img, orden, PASOS)
            except Exception as e:  # noqa: BLE001
                if _es_cuota(e):
                    cuota_en.append(comollama)
                    dichos.append(f"{espacio} ({comollama}): sin cuota de ZeroGPU")
                    continue
                dichos.append(f"{espacio} ({comollama}): {type(e).__name__}: {str(e)[:180]}")
                continue
            if ruta is None:
                motivos = api if isinstance(api, list) else [str(api)]
                if any(_es_cuota(m) for m in motivos):
                    cuota_en.append(comollama)
                    dichos.append(f"{espacio} ({comollama}): sin cuota de ZeroGPU")
                    continue
                dichos.append(f"{espacio} ({comollama}): " + "; ".join(motivos)[:220])
                continue
            # La cuota se mide en segundos de GPU, no en imágenes: sin esto no
            # hay forma de saber cuántas fotos caben en un día.
            GASTO.append({"espacio": espacio, "api": api, "segundos": segundos,
                          "pasos": PASOS})
            log(f"{espacio} · {api} · {segundos}s · {PASOS} pasos")
            from io import BytesIO
            b = BytesIO()
            Image.open(ruta).convert("RGB").save(b, "JPEG", quality=94)
            return b.getvalue(), None
        if cuota_en and len(cuota_en) == len(vias):
            cuotas += 1

    # Basta con que UN espacio diga que no queda cuota.
    #
    # La condición anterior era `cuotas == intentadas`, es decir, que lo
    # dijeran todos. Con un solo espacio en la lista daba igual, pero al poner
    # varios dejó de cumplirse: uno contestaba «sin cuota» y otro daba un
    # error suyo, así que no se levantaba SinCuota y el que llama repetía la
    # tanda seis veces contra una pared. Pasó hoy a las 13:21.
    #
    # Y es que la cuota de ZeroGPU es UNA por cuenta y la comparten todos los
    # espacios: si uno dice que no queda, no queda en ninguno. Lo comprobé el
    # viernes probando treinta.
    if cuotas:
        raise SinCuota(
            "Hugging Face no deja generar más hoy: " + "; ".join(dichos)[:2000])
    return None, dichos


def _primera_imagen(resultado):
    """Gradio devuelve una ruta, una lista o un diccionario, según el espacio."""
    pendientes = [resultado]
    while pendientes:
        x = pendientes.pop(0)
        if isinstance(x, (list, tuple)):
            pendientes.extend(x)
        elif isinstance(x, dict):
            pendientes.extend(x.values())
        elif isinstance(x, str) and Path(x).exists() and \
                Path(x).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            return x
    return None


def pedir(escena, semilla, p, parte):
    """Pide una foto: primero a Kontext, luego a Gemini, y si no, a Pollinations.

    Devuelve (bytes, None) o (None, qué dijo cada sitio)."""
    dichos = []

    datos, fallos = kontext(escena, p)
    if datos:
        if parte == 1:
            log("Fotos generadas con FLUX.1 Kontext (Hugging Face)")
        return datos, None
    dichos += [f"Kontext · {x}" for x in (fallos or [])]

    try:
        ref = foto_referencia(p["referencia_url"])
        orden = ("Keep the face, hair and skin tone of the woman in the reference photo "
                 "exactly as they are — it must be unmistakably the same person. "
                 f"Place her in this new scene: {escena}. "
                 f"Photorealistic smartphone photo, natural skin, soft natural light, "
                 f"{CARA}, {ANATOMIA}. Vertical portrait, 4:5. "
                 "No text, no watermark, no logos anywhere in the image.")
        datos, fallos = gemini.imagen(orden, referencia=ref)
        if datos:
            if parte == 1:
                log("Fotos generadas con Gemini")
            return datos, None
        dichos += [f"Gemini · {x}" for x in (fallos or [])]
    except requests.RequestException as e:
        dichos.append(f"Gemini: no se pudo bajar la foto de referencia ({type(e).__name__})")
    except gemini.GeminiError as e:
        dichos.append(f"Gemini: {str(e)[:150]}")

    clave = os.environ.get("POLLINATIONS_KEY", "")
    texto = quote(frase(escena, p))
    for nombre, plantilla, con_clave in PUERTAS:
        if con_clave and not clave:
            dichos.append(f"{nombre}: no hay POLLINATIONS_KEY en los secretos")
            continue
        url = plantilla.format(t=texto)
        pars = {"model": p.get("modelo_imagen", "kontext"), "width": 1080, "height": 1350,
                "seed": semilla, "nologo": "true", "image": p["referencia_url"]}
        cab = {"User-Agent": "Mozilla/5.0"}
        if con_clave:
            cab["Authorization"] = f"Bearer {clave}"
        try:
            r = requests.get(url, params=pars, headers=cab, timeout=300)
        except requests.RequestException as e:
            dichos.append(f"{nombre}: no se pudo conectar ({type(e).__name__})")
            continue
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            if len(r.content) < 20000:
                dichos.append(f"{nombre}: imagen de {len(r.content)} bytes, demasiado pequeña")
                continue
            if nombre != PUERTAS[0][0]:
                log(f"Foto {parte}: ha respondido «{nombre}»")
            return r.content, None
        espera = r.headers.get("Retry-After")
        dichos.append(f"{nombre}: HTTP {r.status_code} · {r.text[:160].strip()}")
        if r.status_code == 429 and espera and espera.isdigit():
            time.sleep(min(int(espera), 180))
    return None, dichos


TROZOS_DE_MANO = (
    "holding", "holds", "brush", "pen", "pencil", "cup", "mug", "glass",
    "phone", "camera", "book", "leash", "bag", "fork", "spoon", "knife",
    "flower", "umbrella", "racket", "ball",
    # Las manos nombradas directamente. Faltaban, y eso costó seis intentos
    # seguidos el 14 de octubre: la escena decía «hands on the counter», no
    # encajaba con ninguna palabra de arriba, así que se quedaba en el texto
    # y encima se le añadía «hands out of frame». Un encargo que se contradice
    # a sí mismo, y el generador resolvía la contradicción dibujando manos
    # imposibles que el revisor rechazaba una y otra vez.
    "hand", "hands", "finger", "palm", "wrist", "touching", "resting on",
    "leaning on", "typing", "writing", "pointing", "waving", "adjusting",
)


def sin_manos(escena):
    """Quita de la escena lo que obliga a dibujar una mano agarrando algo."""
    limpia = escena
    for pieza in escena.split(", "):
        if any(w in pieza.lower() for w in TROZOS_DE_MANO):
            limpia = limpia.replace(pieza + ", ", "").replace(", " + pieza, "")
    if limpia.strip() in ("", escena.strip()):
        limpia = escena
    return (limpia.rstrip(". ") +
            ", hands out of frame, nothing held in her hands, "
            "arms relaxed, framed from the chest up")


def descargar_fotos(escenas, p):
    """Genera cada foto y la revisa con Gemini: si tiene tres piernas, manos raras o
    cualquier otro fallo típico de la IA, la descarta y prueba otra vez."""
    TRABAJO.mkdir(exist_ok=True)
    base = int(datetime.now(timezone.utc).strftime("%Y%m%d")) * 10
    rutas, descartadas = [], []
    for i, escena in enumerate(escenas):
        destino = TRABAJO / f"foto{i}.jpg"
        mejor, dichos = None, []
        for intento in range(INTENTOS):
            semilla = base + i + intento * 137
            datos, fallos = pedir(escena, semilla, p, i + 1)
            if datos is None:
                dichos = fallos
                log(f"Foto {i + 1}, intento {intento + 1}: " + " | ".join(fallos))
                time.sleep(ESPERAS[intento])
                continue
            mejor = datos
            ok, problema = gemini.revisar_imagen(datos, referencia_bytes(p))
            if ok:
                destino.write_bytes(datos)
                rutas.append(destino)
                log(f"Foto {i + 1} de {len(escenas)} lista y revisada")
                break
            descartadas.append(f"foto {i + 1}: {problema}")
            log(f"Foto {i + 1} descartada ({problema}); genero otra")
            # Insistir seis veces con la misma escena no sirve de nada.
            #
            # El reel de esta semana se cayó así: la escena pedía a Allie
            # pintando, y las seis salieron con los dedos de la mano del
            # pincel deformes. No es mala suerte: una mano agarrando un
            # objeto fino es lo que peor hace cualquier generador. A la
            # segunda, se quita de la escena lo que la está rompiendo.
            if intento == 1:
                escena = sin_manos(escena)
                log(f"Foto {i + 1}: quito las manos de la escena y pruebo así")
            elif intento == 3:
                # Si a la cuarta siguen saliendo mal, se cierra el plano hasta
                # donde no hay manos que dibujar. Una foto de cara y hombros
                # es menos lucida que un plano de medio cuerpo, pero sale.
                escena = (escena.split(",")[0].rstrip(". ") +
                          ", tight close-up portrait, head and shoulders only, "
                          "hands not visible, shoulders and face fill the frame")
                log(f"Foto {i + 1}: cierro el plano a cara y hombros")
            time.sleep(3)
        else:
            if mejor is None:
                raise RuntimeError(
                    "Nadie ha devuelto ninguna imagen. Esto es lo que contestó cada "
                    "sitio en el último intento:\n\n  · "
                    + "\n  · ".join(dichos)
                    + f"\n\nLa foto de referencia que se le manda ({p['referencia_url']}) "
                    + f"responde: {estado_referencia(p['referencia_url'])}"
                    + f"\n\nModelos de imagen que ofrece tu clave de Gemini:\n  "
                    + gemini.modelos_de_imagen())
            # Una escena que no sale no puede tirar el reel entero.
            #
            # Antes, si la cuarta foto fallaba, se perdían también las tres
            # buenas y la semana se quedaba sin vídeo. Tres fotos hacen un
            # reel perfectamente; dos, no.
            log(f"Foto {i + 1}: me rindo con esta escena y sigo con las demás")
    if descartadas:
        log(f"Descartadas por fallos: {len(descartadas)}")
    if len(rutas) < 3:
        raise RuntimeError(
            f"Solo {len(rutas)} de {len(escenas)} fotos pasaron la revisión, y con "
            f"menos de tres no hay reel. Motivos: " + " | ".join(descartadas[-4:]))
    log(f"{len(rutas)} de {len(escenas)} fotos aprobadas")
    return rutas


# ------------------------------------------------------------- para revisar
def guardar_para_revisar(rutas):
    """Deja las cuatro fotos sueltas en videos/fotos/ antes de montarlas.

    Dentro del vídeo la cara se ve un segundo y en movimiento, y así es
    imposible decir si la boca ha salido bien. Sueltas y a tamaño completo, sí.
    Se sobreescriben cada semana, así que no engordan el repositorio.
    """
    carpeta = VIDEOS / "fotos"
    carpeta.mkdir(parents=True, exist_ok=True)
    for viejo in carpeta.glob("*.jpg"):
        viejo.unlink()
    for i, r in enumerate(rutas, 1):
        (carpeta / f"foto{i}.jpg").write_bytes(Path(r).read_bytes())
    log(f"Las {len(rutas)} fotos quedan en videos/fotos/ para poder mirarlas")


# ------------------------------------------------------------------ montaje
def componer(rutas):
    TRABAJO.mkdir(exist_ok=True)   # la creaba descargar_fotos, que ahora se puede saltar
    """Cada foto 4:5 sobre un fondo desenfocado, para llenar el 9:16 sin recortar a Allie."""
    salidas = []
    for i, r in enumerate(rutas):
        src = Image.open(r).convert("RGB")
        s = max(W / src.width, H / src.height) * 1.15
        fondo = src.resize((int(src.width * s), int(src.height * s)), Image.LANCZOS)
        fondo = fondo.filter(ImageFilter.GaussianBlur(40))
        x, y = (fondo.width - W) // 2, (fondo.height - H) // 2
        fondo = fondo.crop((x, y, x + W, y + H))
        frente = src.resize((W, int(src.height * W / src.width)), Image.LANCZOS)
        fondo.paste(frente, (0, (H - frente.height) // 2))
        # Un poco más grande que el encuadre final, para poder desplazar la imagen
        grande = fondo.resize((int(W * 1.2), int(H * 1.2)), Image.LANCZOS)
        destino = TRABAJO / f"comp{i}.jpg"
        grande.save(destino, "JPEG", quality=94)
        salidas.append(destino)
    return salidas


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def montar(compuestas):
    movimientos = [("(iw-%d)*t/%s" % (W, DUR), "(ih-%d)*0.5" % H),
                   ("(iw-%d)*(1-t/%s)" % (W, DUR), "(ih-%d)*0.35" % H),
                   ("(iw-%d)*0.5" % W, "(ih-%d)*t/%s" % (H, DUR)),
                   ("(iw-%d)*0.5" % W, "(ih-%d)*(1-t/%s)" % (H, DUR))]
    clips = []
    for i, c in enumerate(compuestas):
        x, y = movimientos[i % len(movimientos)]
        clip = TRABAJO / f"clip{i}.mp4"
        ff("-loop", "1", "-t", str(DUR), "-i", str(c),
           "-vf", f"crop={W}:{H}:x='{x}':y='{y}',format=yuv420p,setsar=1",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30", str(clip))
        clips.append(clip)

    entradas, filtros, etiqueta = [], [], "0"
    for c in clips:
        entradas += ["-i", str(c)]
    for i in range(1, len(clips)):
        salida = f"x{i}" if i < len(clips) - 1 else "v"
        offset = round(i * DUR - i * FUNDIDO, 2)
        filtros.append(f"[{etiqueta}][{i}]xfade=transition=fade:duration={FUNDIDO}:offset={offset}[{salida}]")
        etiqueta = salida
    sin_audio = TRABAJO / "v.mp4"
    ff(*entradas, "-filter_complex", ";".join(filtros),
       "-map", f"[{etiqueta}]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
       "-r", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(sin_audio))

    # Instagram exige pista de audio: se añade una en silencio
    VIDEOS.mkdir(exist_ok=True)
    final = VIDEOS / f"reel_{datetime.now(timezone.utc):%Y%m%d_%H%M}.mp4"
    ff("-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-i", str(sin_audio),
       "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(final))
    return final


# ------------------------------------------------------------------ subida
def subir(ruta, dichos=None):
    """Lo sube a un alojamiento público, que es lo único que acepta Metricool.

    Los dos repositorios son privados, así que un enlace de GitHub no vale:
    hace falta una dirección que cualquiera pueda abrir sin estar dentro.

    Hay varios sitios porque desde los servidores de GitHub unos responden y
    otros no, y cambia de un día para otro. Lo que diga cada uno se guarda en
    «dichos», que acaba en la propuesta: si fallan todos, al menos se sabe por
    qué en vez de quedarse con «no se pudo subir».
    """
    dichos = dichos if dichos is not None else []

    def catbox(f):
        return requests.post("https://catbox.moe/user/api.php",
                             data={"reqtype": "fileupload"},
                             files={"fileToUpload": f}, timeout=300).text.strip()

    def litterbox(f):
        return requests.post("https://litterbox.catbox.moe/resources/internals/api.php",
                             data={"reqtype": "fileupload", "time": "72h"},
                             files={"fileToUpload": f}, timeout=300).text.strip()

    def tmpfiles(f):
        r = requests.post("https://tmpfiles.org/api/v1/upload",
                          files={"file": f}, timeout=300)
        url = (r.json().get("data") or {}).get("url", "")
        # el enlace que devuelve es la página; el fichero está en /dl/
        return url.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1) if url else ""

    def uguu(f):
        r = requests.post("https://uguu.se/upload", files={"files[]": f}, timeout=300)
        d = r.json()
        archivos = d.get("files") or []
        return archivos[0].get("url", "") if archivos else ""

    def cero(f):
        return requests.post("https://0x0.st", files={"file": f},
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=300).text.strip()

    for nombre, fn in (("litterbox", litterbox), ("catbox", catbox),
                       ("tmpfiles", tmpfiles), ("uguu", uguu), ("0x0", cero)):
        try:
            with open(ruta, "rb") as f:
                url = fn(f)
        except Exception as e:  # noqa: BLE001
            dichos.append(f"{nombre}: {type(e).__name__} {str(e)[:120]}")
            log(f"{nombre} falló: {e}")
            continue
        if isinstance(url, str) and url.startswith("http"):
            # Que devuelva una dirección no quiere decir que esa dirección sea
            # la imagen: algunos sitios dan la página que la enseña. Metricool
            # se lo tragó y contestó «failed to normalize media». Se comprueba
            # que lo que hay al otro lado es una imagen antes de darla por
            # buena.
            try:
                c = requests.get(url, timeout=60, stream=True,
                                 headers={"User-Agent": "Mozilla/5.0"})
                tipo = c.headers.get("content-type", "")
                largo = int(c.headers.get("content-length") or 0)
                c.close()
            except Exception as e:  # noqa: BLE001
                dichos.append(f"{nombre}: dio {url} pero no se pudo abrir ({type(e).__name__})")
                continue
            if c.status_code == 200 and largo > 20000 and (
                    tipo.startswith("image/") or tipo.startswith("video/")):
                log(f"Subido a {nombre}: {url} ({tipo}, {largo // 1024} KB)")
                return url
            dichos.append(f"{nombre}: {url} devuelve HTTP {c.status_code}, "
                          f"{tipo or 'sin tipo'}, {largo} bytes — no es imagen ni vídeo")
            log(f"{nombre}: la dirección no sirve ({tipo}, {largo} bytes)")
            continue
        dichos.append(f"{nombre}: respondió «{str(url)[:120]}»")
        log(f"{nombre} respondió: {str(url)[:150]}")
    raise RuntimeError("Ningún alojamiento aceptó el archivo · " + " | ".join(dichos))


# ------------------------------------------------------------------ aviso
def issue(titulo, cuerpo):
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        return
    try:
        requests.post(f"https://api.github.com/repos/{repo}/issues", timeout=60,
                      headers={"Authorization": f"Bearer {token}",
                               "Accept": "application/vnd.github+json"},
                      json={"title": titulo, "body": cuerpo, "labels": ["reel"]})
    except requests.RequestException as e:
        log(f"No se pudo crear el aviso: {e}")


def texto_de_las_fotos(p, rutas, idea_previa=""):
    """El texto del post, escrito MIRANDO las fotos que van en el vídeo.

    Por qué existe. guion() escribe el texto ANTES de que las fotos existan,
    a partir de un tema elegido al azar. Y en el camino pasan tres cosas que
    lo desconectan de lo que se ve:
      · una escena rechazada por el revisor se reintenta cambiada,
      · sin_manos() borra de la escena el objeto que sujetaba,
      · y sobre todo, el reel se monta con fotos del BANCO, que pueden ser
        de otra tanda y de otro tema completamente distinto.

    El 15 de octubre el texto hablaba de «brochas, colores y manchas de
    pintura» sobre tres fotos de Allie en una cafetería. No había un pincel
    en ninguna. Publicar eso es peor que no publicar: a quien lo lee le
    chirría aunque no sepa decir por qué.

    Así que el texto se escribe al final, con las fotos delante.
    """
    imagenes = []
    for r in rutas[:4]:
        try:
            imagenes.append(Path(r).read_bytes())
        except Exception as e:  # noqa: BLE001
            log(f"No pude leer {r} para escribir el texto: {e}")
    if not imagenes:
        return None

    prompt = f"""Eres el community manager de {p.get('nombre', 'Allie')} en Instagram.
Su forma de ser: {p.get('personalidad', '')}

Te paso las {len(imagenes)} fotos que forman el reel. Escribe el texto del post.

REGLA PRINCIPAL: solo puedes mencionar cosas que SE VEAN en las fotos. Si no
hay un café en la imagen, no hables de café. Si no hay pinceles, no hables de
pintar. Si no se ve la calle, no digas que está paseando. Es preferible un
texto sobre cómo se siente o qué está pensando, que uno que invente objetos o
planes que no están. Mira la ropa, el sitio, la luz y la postura, y escribe
desde ahí.

Primera línea con gancho. Tres o cuatro líneas en total. Termina con una
pregunta abierta y fácil de contestar. Primera persona, cercano, nada de
lenguaje de marca. Nada de comillas.

Devuelve SOLO un JSON:
{{"texto": "...", "hashtags": ["#...", "..."], "idea": "la idea en una frase en español"}}

Reglas: 4 o 5 hashtags, incluye {p.get('hashtags_base', ['#Allie', '#AIInfluencer'])}."""
    try:
        g = gemini.json_(prompt, imagenes=imagenes)
    except Exception as e:  # noqa: BLE001
        log(f"No pude escribir el texto mirando las fotos: {e}")
        return None
    if not (g.get("texto") or "").strip():
        return None
    return g


def main():
    p = persona()
    log("Pensando la idea del reel…")
    g = guion(p)
    log(f"Idea: {g.get('idea')}")
    if os.environ.get("SOLO_MONTAR") == "si":
        # Las fotos ya están generadas y revisadas; lo único que falta es el
        # vídeo. Volver a generarlas gastaría cupo para repetir un trabajo ya
        # hecho, y el cupo diario es justo lo que se acaba.
        rutas = sorted((BASE / "videos" / "fotos").glob("*.jpg"))
        if len(rutas) < 3:
            raise RuntimeError(f"Solo hay {len(rutas)} fotos guardadas; hacen falta 3.")
        log(f"Monto con las {len(rutas)} fotos que ya estaban revisadas")
    else:
        rutas = descargar_fotos(g["escenas"], p)
        guardar_para_revisar(rutas)
    # El texto, AHORA, con las fotos delante. Si falla, se queda el de
    # guion(), que es peor pero mejor que nada.
    mirado = texto_de_las_fotos(p, rutas, g.get("idea", ""))
    if mirado:
        g["texto"] = mirado.get("texto") or g.get("texto", "")
        g["hashtags"] = mirado.get("hashtags") or g.get("hashtags", [])
        g["idea"] = mirado.get("idea") or g.get("idea", "")
        log("Texto reescrito mirando las fotos del reel")
    else:
        log("AVISO: el texto no se pudo escribir mirando las fotos; va el del guion")

    compuestas = componer(rutas)
    video = montar(compuestas)
    log(f"Vídeo montado: {video.name} ({video.stat().st_size // 1024} KB)")
    url = subir(video)

    hashtags = " ".join(h if str(h).startswith("#") else f"#{h}" for h in g.get("hashtags", []))
    datos = {"url": url, "archivo": video.name, "idea": g.get("idea", ""), "tema": g.get("tema", ""),
             "texto": g.get("texto", ""), "hashtags": hashtags,
             "creado": datetime.now(timezone.utc).isoformat(), "programado": False}
    (VIDEOS / "ultimo.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    issue(f"🎬 Reel listo · {g.get('idea', '')[:60]}",
          f"**Idea:** {g.get('idea', '')}\n\n**Vídeo:** {url}\n\n**Texto propuesto:**\n\n{g.get('texto', '')}\n\n"
          f"{hashtags}\n\n_Claude lo programará en Metricool como Trial Reel._")
    log("Listo.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        # El fichero primero. Los avisos dejan de crearse cuando se abren
        # muchos seguidos —GitHub lo corta sin decir nada— y entonces el fallo
        # se queda solo en el registro, que no se puede leer desde fuera.
        # Un fichero en el repositorio sí se lee siempre.
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n\n{detalle}\n",
            encoding="utf-8")
        issue("⚠️ No se pudo montar el reel", f"Error: `{e}`\n\nSi no sabes qué significa, "
                                               "copia este mensaje y pregúntale a Claude.")
        sys.exit(1)
