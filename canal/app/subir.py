"""Subir el vídeo montado a YouTube, sin tocar nada a mano.

POR QUÉ ESTO NO EXISTÍA. El README del canal dice, y durante años fue verdad:
«No sube a YouTube. Los vídeos subidos por API sin verificar quedan bloqueados
como privados y no se puede apelar». Esa regla es de julio de 2020 y era el
único motivo de que el canal necesitara a una persona delante. Por eso se
quedó parado el 10 de octubre: la fábrica entera es automática menos el último
metro.

YA NO ES VERDAD. Comprobado el 20 de octubre de 2026 en la documentación
oficial, en tres páginas distintas:

  · videos/insert: «Videos uploaded from unverified API projects are not
    restricted to private viewing mode.»
  · videos/insert: «Quota impact: 100 calls per day. A call to this method has
    a quota cost of 1 unit in the Video Uploads quota bucket.»
  · determine_quota_cost: las subidas tienen su propio cubo de cuota y no
    gastan de las 10.000 unidades diarias del resto de la API.

O sea: cien vídeos al día, gratis, públicos, sin auditoría. La puerta que
estaba cerrada está abierta.

PERO NO ME FÍO DE LA DOCUMENTACIÓN. La lección más cara de este mes fue que
arreglar la fábrica no vacía el almacén: hay que mirar la SALIDA, no el
código. Así que después de subir, este programa le PREGUNTA A YOUTUBE en qué
estado quedó el vídeo —privacyStatus, uploadStatus, rejectionReason— y lo
escribe. Si Google volviera a bloquearlo como privado, se ve en el registro
el mismo día y no tres semanas después.

CÓMO SE AUTENTICA. Con un token de refresco de OAuth, que no caduca mientras
no se revoque. Tres secretos en el repositorio: YT_CLIENT_ID, YT_CLIENT_SECRET
y YT_REFRESH_TOKEN. Nunca se imprimen, ni enteros ni en trozos, ni siquiera
cuando algo falla: lo que se escribe en estado/ acaba en un commit.

NO HACE FALTA NINGUNA LIBRERÍA DE GOOGLE. La API es HTTP normal y `requests`
ya estaba en requirements.txt. Una dependencia menos que se rompa.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

BASE = Path(__file__).resolve().parent.parent

TOKEN = "https://oauth2.googleapis.com/token"
SUBIDA = "https://www.googleapis.com/upload/youtube/v3/videos"
MINIATURA = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
CONSULTA = "https://www.googleapis.com/youtube/v3/videos"

# Límites que YouTube rechaza sin contemplaciones. Mejor cortar aquí, con un
# aviso, que recibir un 400 después de haber subido ciento y pico megas.
TOPE_TITULO = 100
TOPE_DESCRIPCION = 5000
TOPE_ETIQUETAS = 500      # la suma de todas, no cada una
TOPE_MINIATURA = 2 * 1024 * 1024

# 28 = Science & Technology. 25 = News & Politics. Se puede cambiar por vídeo.
CATEGORIA = "28"


class SinCredenciales(RuntimeError):
    pass


def log(m):
    print(f"· {m}", flush=True)


def credenciales():
    """Las tres claves, o un error que dice cuál falta sin enseñar ninguna."""
    faltan = [n for n in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
              if not (os.environ.get(n) or "").strip()]
    if faltan:
        raise SinCredenciales(
            "Faltan estos secretos en el repositorio: " + ", ".join(faltan) +
            ". Están en Settings → Secrets and variables → Actions.")
    return (os.environ["YT_CLIENT_ID"].strip(),
            os.environ["YT_CLIENT_SECRET"].strip(),
            os.environ["YT_REFRESH_TOKEN"].strip())


def acceso():
    """Cambia el token de refresco por uno de acceso, que dura una hora."""
    cid, secreto, refresco = credenciales()
    r = requests.post(TOKEN, timeout=60, data={
        "client_id": cid, "client_secret": secreto,
        "refresh_token": refresco, "grant_type": "refresh_token"})
    if r.status_code != 200:
        # El cuerpo de Google en este punto no lleva el token, pero sí puede
        # llevar el client_id. Me quedo solo con el código de error.
        try:
            motivo = r.json().get("error", "sin detalle")
        except Exception:  # noqa: BLE001
            motivo = "respuesta ilegible"
        raise RuntimeError(
            f"Google no acepta el token de refresco ({r.status_code}: {motivo}). "
            "Si pone invalid_grant, el token se revocó y hay que sacar otro.")
    t = r.json().get("access_token")
    if not t:
        raise RuntimeError("Google contestó sin token de acceso.")
    log("Autenticado")
    return t


def ficha():
    """Título, descripción y etiquetas del vídeo: videos/<id>/youtube.yml.

    Si no existe, se saca del guion: el título es el encabezado `# …` y la
    descripción, las dos primeras frases. Vale para salir del paso, pero el
    título es la mitad de lo que decide si alguien hace clic, así que lo
    normal es escribirlo a mano en el yml.
    """
    # Un Short no vive en videos/<id>/: su ficha la escribe app/corto.py en
    # cortos/salida/<id>.yml. Con FICHA se le dice cuál leer.
    suelta = (os.environ.get("FICHA") or "").strip()
    if suelta:
        f = Path(suelta)
        if not f.exists():
            raise RuntimeError(f"No está la ficha: {f}")
        return yaml.safe_load(f.read_text(encoding="utf-8")) or {}

    f = config.ruta("youtube.yml")
    if f.exists() and f.name == "youtube.yml":
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    else:
        d = {}

    if not d.get("titulo"):
        g = config.guion()
        if g and g.exists():
            for linea in g.read_text(encoding="utf-8").splitlines():
                if linea.startswith("# "):
                    d["titulo"] = linea[2:].strip()
                    break
    return d


def recortar(d):
    """Ajusta a los límites de YouTube y avisa de cada recorte."""
    titulo = (d.get("titulo") or "").strip()
    if not titulo:
        raise RuntimeError(
            "Sin título no se sube. Escribe `titulo:` en videos/<id>/youtube.yml.")
    # Un < o un > en el título hace que YouTube devuelva 400 sin explicar nada.
    titulo = titulo.replace("<", "‹").replace(">", "›")
    if len(titulo) > TOPE_TITULO:
        log(f"Título de {len(titulo)} caracteres: lo corto a {TOPE_TITULO}")
        titulo = titulo[:TOPE_TITULO - 1].rstrip() + "…"

    desc = (d.get("descripcion") or "").replace("<", "‹").replace(">", "›")
    if len(desc) > TOPE_DESCRIPCION:
        log(f"Descripción de {len(desc)} caracteres: la corto a {TOPE_DESCRIPCION}")
        desc = desc[:TOPE_DESCRIPCION - 1].rstrip() + "…"

    etiquetas, total = [], 0
    for e in (d.get("etiquetas") or []):
        e = str(e).strip()
        if not e:
            continue
        # YouTube cuenta las comas, y una etiqueta con espacios cuenta dos más
        # por las comillas que le pone él.
        cuesta = len(e) + 1 + (2 if " " in e else 0)
        if total + cuesta > TOPE_ETIQUETAS:
            log(f"Etiquetas por encima de {TOPE_ETIQUETAS} caracteres: "
                f"me quedo con las {len(etiquetas)} primeras")
            break
        etiquetas.append(e)
        total += cuesta
    return titulo, desc, etiquetas


def cuerpo(d, privacidad):
    titulo, desc, etiquetas = recortar(d)
    log(f"Título: {titulo}")
    log(f"Descripción: {len(desc)} caracteres · {len(etiquetas)} etiquetas")
    log(f"Privacidad: {privacidad}")
    return {
        "snippet": {
            "title": titulo,
            "description": desc,
            "tags": etiquetas,
            "categoryId": str(d.get("categoria") or CATEGORIA),
            # Sin esto YouTube adivina el idioma por el audio y a veces se
            # equivoca; equivocarse aquí hunde la recomendación.
            "defaultLanguage": d.get("idioma") or "en",
            "defaultAudioLanguage": d.get("idioma") or "en",
        },
        "status": {
            "privacyStatus": privacidad,
            # Obligatorio desde la ley de protección de menores. Si no se
            # declara, YouTube rechaza la subida entera.
            "selfDeclaredMadeForKids": bool(d.get("para_ninos", False)),
            "embeddable": True,
        },
    }


def subir(token, mp4, metadatos):
    """Subida reanudable: primero se abre la sesión, luego van los bytes."""
    tam = mp4.stat().st_size
    log(f"{mp4.name} · {tam / 1e6:.1f} MB")

    r = requests.post(
        SUBIDA, timeout=120,
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Length": str(tam),
                 "X-Upload-Content-Type": "video/mp4"},
        data=json.dumps(metadatos).encode("utf-8"))
    if r.status_code not in (200, 201):
        raise RuntimeError(f"YouTube no abre la sesión de subida "
                           f"({r.status_code}): {r.text[:400]}")
    sesion = r.headers.get("Location")
    if not sesion:
        raise RuntimeError("YouTube abrió la sesión pero no dijo dónde subir.")
    log("Sesión de subida abierta")

    datos = mp4.read_bytes()
    desde = 0
    for intento in range(5):
        trozo = datos[desde:]
        p = requests.put(
            sesion, data=trozo, timeout=1800,
            headers={"Content-Length": str(len(trozo)),
                     "Content-Range": f"bytes {desde}-{tam - 1}/{tam}"})
        if p.status_code in (200, 201):
            v = p.json()
            log(f"Subido · {v.get('id')}")
            return v.get("id")
        if p.status_code in (500, 502, 503, 504, 308):
            # 308 = le faltan bytes. Le pregunto por dónde iba en vez de
            # empezar de cero, que es lo que hace útil una subida reanudable.
            espera = 2 ** intento
            log(f"{p.status_code}: reintento en {espera}s")
            time.sleep(espera)
            q = requests.put(sesion, timeout=120,
                             headers={"Content-Length": "0",
                                      "Content-Range": f"bytes */{tam}"})
            if q.status_code in (200, 201):
                return q.json().get("id")
            rango = q.headers.get("Range")
            desde = int(rango.split("-")[1]) + 1 if rango else 0
            continue
        raise RuntimeError(f"YouTube rechazó la subida ({p.status_code}): "
                           f"{p.text[:400]}")
    raise RuntimeError("Cinco intentos y la subida no terminó.")


def poner_miniatura(token, video_id, imagen):
    if not imagen or not Path(imagen).exists():
        log("Sin miniatura: YouTube elegirá un fotograma")
        return False
    f = Path(imagen)
    if f.stat().st_size > TOPE_MINIATURA:
        log(f"La miniatura pesa {f.stat().st_size / 1e6:.1f} MB y el tope son 2: "
            "la dejo sin poner")
        return False
    tipo = "image/png" if f.suffix.lower() == ".png" else "image/jpeg"
    r = requests.post(MINIATURA, timeout=120, params={"videoId": video_id},
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": tipo},
                      data=f.read_bytes())
    if r.status_code == 200:
        log(f"Miniatura puesta: {f.name}")
        return True
    # Una miniatura que falla no debe tirar una subida que salió bien.
    log(f"La miniatura no entró ({r.status_code}): {r.text[:200]}")
    return False


def comprobar(token, video_id):
    """Preguntarle a YouTube cómo quedó. Esto es lo importante.

    La documentación dice que ya no bloquea los vídeos como privados. La
    documentación no es la salida: la salida es esto.
    """
    for intento in range(6):
        time.sleep(5)
        r = requests.get(CONSULTA, timeout=60,
                         params={"part": "status,snippet,processingDetails",
                                 "id": video_id},
                         headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            log(f"No puedo consultar el estado ({r.status_code})")
            continue
        items = r.json().get("items") or []
        if not items:
            continue
        s = items[0].get("status") or {}
        estado = {"id": video_id,
                  "enlace": f"https://www.youtube.com/watch?v={video_id}",
                  "privacidad": s.get("privacyStatus"),
                  "subida": s.get("uploadStatus"),
                  "rechazo": s.get("rejectionReason"),
                  "titulo": (items[0].get("snippet") or {}).get("title")}
        log(f"Estado: privacidad={estado['privacidad']} · "
            f"subida={estado['subida']} · rechazo={estado['rechazo'] or 'ninguno'}")
        if estado["subida"] in ("processed", "rejected", "failed"):
            return estado
        if intento == 5:
            return estado
    return {"id": video_id, "enlace": f"https://www.youtube.com/watch?v={video_id}",
            "privacidad": None, "subida": "sin respuesta", "rechazo": None}


def main():
    # Modo llave: comprobar que el token de refresco sigue vivo, y nada más.
    #
    # POR QUÉ EXISTE ESTO. La documentación de Google dice, literalmente:
    # «A Google Cloud Platform project with an OAuth consent screen configured
    # for an external user type and a publishing status of "Testing" is issued
    # a refresh token expiring in 7 days». Si la aplicación se queda en
    # «Testing», el canal se muere solo el martes siguiente y no avisa nadie.
    # Por eso hay un workflow que llama aquí todos los lunes: así un token
    # muerto se descubre un lunes por la mañana y no el día que tocaba vídeo.
    if (os.environ.get("SOLO_LLAVE") or "").strip().lower() in ("si", "sí", "true", "1"):
        acceso()
        log("La llave de YouTube sigue viva.")
        return

    seco = (os.environ.get("EN_SECO") or "").strip().lower() in ("si", "sí", "true", "1")

    # En seco NO hace falta el mp4. Revisar el título y la descripción tiene
    # que poderse hacer antes de gastar hora y media de montaje, no después.
    mp4 = Path(os.environ.get("MP4") or (BASE / "video" / "primer-corte.mp4"))
    if not mp4.exists():
        if not seco:
            raise RuntimeError(f"No está el vídeo: {mp4}. Móntalo antes.")
        log(f"(No está {mp4.name}, pero en seco da igual: aquí solo se mira la ficha)")

    privacidad = (os.environ.get("PRIVACIDAD") or "unlisted").strip().lower()
    if privacidad not in ("public", "unlisted", "private"):
        raise RuntimeError(f"Privacidad rara: {privacidad!r}. "
                           "Vale public, unlisted o private.")

    d = ficha()
    log(f"Vídeo: {config.cual()}")
    metadatos = cuerpo(d, privacidad)
    if seco:
        log("EN_SECO: no se sube nada. Esto es lo que se enviaría:")
        print(json.dumps(metadatos, ensure_ascii=False, indent=1), flush=True)
        return

    token = acceso()
    video_id = subir(token, mp4, metadatos)
    mini = d.get("miniatura")
    poner_miniatura(token, video_id, BASE / "miniaturas" / mini if mini else None)
    estado = comprobar(token, video_id)

    estado["cuando"] = datetime.now(timezone.utc).isoformat()
    estado["video"] = config.cual()
    registro = BASE / "estado" / "subidos.json"
    ya = []
    if registro.exists():
        try:
            ya = json.loads(registro.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            ya = []
    ya.append(estado)
    registro.parent.mkdir(parents=True, exist_ok=True)
    registro.write_text(json.dumps(ya, ensure_ascii=False, indent=1), encoding="utf-8")

    log(f"PUBLICADO · {estado['enlace']}")
    if estado.get("privacidad") == "private" and privacidad != "private":
        log("OJO: pedí " + privacidad + " y quedó PRIVATE. Si pasa esto, "
            "Google ha vuelto a bloquear las subidas por API sin auditar.")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "estado").mkdir(parents=True, exist_ok=True)
        (BASE / "estado" / "ULTIMO-FALLO-SUBIDA.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · subida\n\n{detalle}\n",
            encoding="utf-8")
        raise
