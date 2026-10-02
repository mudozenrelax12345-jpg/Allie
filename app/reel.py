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
Contenido apto para todos los públicos.
Reglas para el texto: 4 o 5 hashtags, incluye {p.get('hashtags_base', ['#Allie', '#AIInfluencer'])}."""
    g = gemini.json_(prompt)
    escenas = (g.get("escenas") or [])[:N_FOTOS]
    while len(escenas) < N_FOTOS:
        escenas.append(escenas[-1] if escenas else tema)
    g["escenas"], g["tema"] = escenas, tema
    return g


# ------------------------------------------------------------------ fotos
ANATOMIA = ("anatomically correct, exactly two arms and two legs, five fingers on each hand, "
            "natural human proportions, no extra limbs, no duplicated body parts, "
            "no deformed hands or feet")


def url_pollinations(escena, semilla, p):
    clave = os.environ.get("POLLINATIONS_KEY", "")
    if not clave:
        raise RuntimeError("Falta el secreto POLLINATIONS_KEY en GitHub.")
    texto = (f"The same young woman from the reference photo, identical face and hair, {escena}. "
             f"Photorealistic smartphone photo, natural skin, soft natural light, {ANATOMIA}, "
             f"vertical 4:5 crop, no text, no watermark")
    return (f"https://gen.pollinations.ai/image/{quote(texto)}?model={p.get('modelo_imagen', 'kontext')}"
            f"&width=1080&height=1350&seed={semilla}&nologo=true"
            f"&image={quote(p['referencia_url'], safe='')}&key={clave}")


INTENTOS = 4


def descargar_fotos(escenas, p):
    """Genera cada foto y la revisa con Gemini: si tiene tres piernas, manos raras o
    cualquier otro fallo típico de la IA, la descarta y prueba otra vez."""
    TRABAJO.mkdir(exist_ok=True)
    base = int(datetime.now(timezone.utc).strftime("%Y%m%d")) * 10
    rutas, descartadas = [], []
    for i, escena in enumerate(escenas):
        destino = TRABAJO / f"foto{i}.jpg"
        mejor = None
        for intento in range(INTENTOS):
            semilla = base + i + intento * 137
            try:
                r = requests.get(url_pollinations(escena, semilla, p), timeout=300)
            except requests.RequestException as e:
                log(f"Foto {i + 1}: fallo de red ({e}); reintento")
                time.sleep(5)
                continue
            if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
                log(f"Foto {i + 1}: Pollinations devolvió {r.status_code} {r.text[:120]}")
                time.sleep(5)
                continue
            mejor = r.content
            ok, problema = gemini.revisar_imagen(r.content)
            if ok:
                destino.write_bytes(r.content)
                rutas.append(destino)
                log(f"Foto {i + 1} de {len(escenas)} lista y revisada")
                break
            descartadas.append(f"foto {i + 1}: {problema}")
            log(f"Foto {i + 1} descartada ({problema}); genero otra")
            time.sleep(3)
        else:
            if mejor is None:
                raise RuntimeError("Pollinations no ha devuelto la imagen. Puede que se haya agotado "
                                   "el saldo gratuito de la semana.")
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
