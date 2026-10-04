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
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
import yaml
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
    tema = random.choice(temas)
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

Reglas para las escenas: en inglés, muy descriptivas (lugar, ropa, pose, expresión, luz, encuadre).
MUY IMPORTANTE con el encuadre: usa planos de medio cuerpo, de cintura para arriba o primeros planos
("upper-body shot", "medium shot from the waist up", "close-up"). NADA de planos de cuerpo entero ni
de cuerpo completo: es donde la IA se inventa piernas y manos de más. Evita también manos en posturas
raras o muy en primer plano. Nada de texto, logotipos ni marcas dentro de la imagen.
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
ESPERAS = [10, 25, 45, 70, 90, 90]


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


def pedir(escena, semilla, p, parte):
    """Pide una foto: primero a Gemini, y si no, a Pollinations.

    Devuelve (bytes, None) o (None, qué dijo cada sitio)."""
    dichos = []
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
            ok, problema = gemini.revisar_imagen(datos)
            if ok:
                destino.write_bytes(datos)
                rutas.append(destino)
                log(f"Foto {i + 1} de {len(escenas)} lista y revisada")
                break
            descartadas.append(f"foto {i + 1}: {problema}")
            log(f"Foto {i + 1} descartada ({problema}); genero otra")
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
            raise RuntimeError(f"Las {INTENTOS} imágenes de la foto {i + 1} salieron con fallos "
                               f"({descartadas[-1]}). Esta semana no monto el reel.")
    if descartadas:
        log(f"Descartadas por fallos: {len(descartadas)}")
    return rutas


# ------------------------------------------------------------------ montaje
def componer(rutas):
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
def subir(ruta):
    """Lo sube a un alojamiento público para que Metricool pueda descargarlo."""
    intentos = [
        ("catbox", lambda f: requests.post("https://catbox.moe/user/api.php",
                                           data={"reqtype": "fileupload"},
                                           files={"fileToUpload": f}, timeout=300).text.strip()),
        ("0x0", lambda f: requests.post("https://0x0.st", files={"file": f},
                                        headers={"User-Agent": "allie-reel/1.0"}, timeout=300).text.strip()),
    ]
    for nombre, fn in intentos:
        try:
            with open(ruta, "rb") as f:
                url = fn(f)
            if url.startswith("http"):
                log(f"Vídeo subido a {nombre}: {url}")
                return url
            log(f"{nombre} respondió: {url[:150]}")
        except Exception as e:  # noqa: BLE001
            log(f"{nombre} falló: {e}")
    raise RuntimeError("No se pudo subir el vídeo a ningún alojamiento público.")


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


def main():
    p = persona()
    log("Pensando la idea del reel…")
    g = guion(p)
    log(f"Idea: {g.get('idea')}")
    rutas = descargar_fotos(g["escenas"], p)
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
        traceback.print_exc()
        issue("⚠️ No se pudo montar el reel", f"Error: `{e}`\n\nSi no sabes qué significa, "
                                               "copia este mensaje y pregúntale a Claude.")
        sys.exit(1)
