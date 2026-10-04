"""Textos con la API de Gemini (el nivel gratuito cubre texto)."""
import base64
import json
import os
import re

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"

# El nivel gratuito limita las peticiones por día, y el límite es distinto en cada
# modelo (los "lite" son los más generosos). Se prueban en orden: si uno se queda
# sin cupo o no existe, se pasa al siguiente sin que el proceso se pare.
MODELOS = [m.strip() for m in os.environ.get(
    "GEMINI_TEXT_MODELS",
    "gemini-3.5-flash-lite,gemini-2.5-flash-lite,gemini-2.0-flash-lite,"
    "gemini-3.5-flash,gemini-2.5-flash,gemini-2.0-flash").split(",") if m.strip()]
if os.environ.get("GEMINI_TEXT_MODEL"):
    MODELOS.insert(0, os.environ["GEMINI_TEXT_MODEL"].strip())

_elegido = None          # modelo que funcionó la última vez
_descartados = set()     # modelos sin cupo o inexistentes en esta ejecución


class GeminiError(Exception):
    pass


def _clave():
    k = os.environ.get("GEMINI_API_KEY", "")
    if not k:
        raise GeminiError("Falta el secreto GEMINI_API_KEY en GitHub.")
    return k


def _post(url, body):
    try:
        r = requests.post(url, headers={"x-goog-api-key": _clave(), "Content-Type": "application/json"},
                          json=body, timeout=120)
    except requests.RequestException as e:
        raise GeminiError(f"No se pudo conectar con Gemini: {e}")
    if r.status_code == 404:
        return None
    try:
        data = r.json()
    except ValueError:
        raise GeminiError(f"Respuesta no válida de Gemini (HTTP {r.status_code})")
    if r.status_code >= 400 or "error" in data:
        raise GeminiError(f"Gemini: {data.get('error', {}).get('message', r.text[:200])}")
    return data


def _textos(nodo, out):
    if isinstance(nodo, dict):
        if nodo.get("type") == "thought" or nodo.get("thought") is True:
            return
        if isinstance(nodo.get("text"), str) and nodo.get("type", "text") == "text":
            out.append(nodo["text"])
        for k, v in nodo.items():
            if k not in ("input", "usage", "usageMetadata"):
                _textos(v, out)
    elif isinstance(nodo, list):
        for v in nodo:
            _textos(v, out)


def _sin_cupo(e):
    m = str(e).lower()
    return any(s in m for s in ("rate limit", "quota", "resource_exhausted", "429",
                                "too many requests"))


def _una_vez(modelo, prompt, imagenes):
    entrada = [{"type": "text", "text": prompt}]
    for b in imagenes:
        entrada.append({"type": "image", "mime_type": "image/jpeg",
                        "data": base64.b64encode(b).decode()})
    data = _post(f"{BASE}/interactions", {"model": modelo, "input": entrada})
    if data is None:
        partes = [{"text": prompt}]
        for b in imagenes:
            partes.append({"inline_data": {"mime_type": "image/jpeg",
                                           "data": base64.b64encode(b).decode()}})
        data = _post(f"{BASE}/models/{modelo}:generateContent",
                     {"contents": [{"role": "user", "parts": partes}]})
    return data


def texto(prompt, imagenes=()):
    """imagenes: lista de bytes JPEG/PNG que Gemini mirará junto al texto."""
    global _elegido
    orden = ([_elegido] if _elegido else []) + [m for m in MODELOS if m != _elegido]
    ultimo = None
    data = None
    for modelo in orden:
        if modelo in _descartados:
            continue
        try:
            data = _una_vez(modelo, prompt, imagenes)
        except GeminiError as e:
            ultimo = e
            if _sin_cupo(e):
                _descartados.add(modelo)
                if _elegido == modelo:
                    _elegido = None
                continue
            raise
        if data is None:          # el modelo no existe
            _descartados.add(modelo)
            continue
        _elegido = modelo
        break
    if data is None:
        raise GeminiError(
            f"Ningún modelo de Gemini disponible. Último aviso: {ultimo}"
            if ultimo else "Ningún modelo de Gemini disponible.")
    out = []
    if isinstance(data.get("steps"), list):
        nodos = [s for s in data["steps"] if s.get("type") == "model_output"] or data["steps"]
    else:
        nodos = data.get("outputs") or data.get("candidates") or data
    _textos(nodos, out)
    return "\n".join(out).strip()


def json_(prompt, imagenes=()):
    t = texto(prompt, imagenes)
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        raise GeminiError("Gemini no devolvió un JSON válido.")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise GeminiError(f"JSON inválido de Gemini: {e}")


REVISION = """Mira esta foto. Es para la cuenta de Instagram de una influencer y se ha generado con IA,
así que puede tener fallos típicos. Revísala con MUCHA atención y responde con sinceridad.

Empieza SIEMPRE mirando la boca y los ojos, ampliando mentalmente la cara. Es donde más
falla la IA y donde más se nota: dientes de más o fusionados, encías deformes, labios
torcidos o asimétricos, una sonrisa que no cuadra con el resto de la cara, ojos de distinto
tamaño o que miran a sitios distintos. Si la boca no es claramente natural, es "ok": false.

Marca "ok": false si ves CUALQUIERA de estos problemas:
- boca, dientes, encías o labios raros, deformes o asimétricos
- ojos asimétricos, de distinto tamaño o con la mirada descuadrada
- número de brazos, piernas, manos o pies distinto del normal (¡mira bien las piernas!)
- dedos de más o de menos, manos o pies deformes
- cara deformada o con asimetrías evidentes
- cuerpos o miembros fusionados con objetos, animales o el fondo
- texto, letras, logotipos o marcas de agua en la imagen
- la imagen está cortada de forma rara, borrosa o es claramente artificial
- animales con el número de patas equivocado
- contenido que no sería apropiado en una cuenta pública

Si todo está bien, responde "ok": true.

Devuelve SOLO un JSON: {"ok": true|false, "problema": "qué has visto, en español, muy breve"}"""


def revisar_imagen(datos):
    """Devuelve (ok, problema). Si Gemini falla, deja pasar la imagen para no bloquear el proceso."""
    try:
        r = json_(REVISION, imagenes=[datos])
    except GeminiError as e:
        return True, f"no se pudo revisar ({e})"
    return bool(r.get("ok")), (r.get("problema") or "").strip()


# --------------------------------------------------------------- imágenes
# Pollinations dejó de hacer gratis el modelo que copia una cara de una foto de
# referencia ("kontext": HTTP 402, saldo cero). Gemini sí lo hace en su nivel
# gratuito y la clave ya está puesta, así que las fotos de Allie se generan
# aquí: se le manda su foto junto al texto y se le pide la misma cara.
IMG_MODELOS = [m.strip() for m in os.environ.get(
    "GEMINI_IMAGE_MODELS",
    "gemini-3-pro-image-preview,gemini-2.5-flash-image,"
    "gemini-2.5-flash-image-preview,gemini-2.0-flash-preview-image-generation"
).split(",") if m.strip()]

_img_elegido = None


def _buscar_imagen(nodo):
    """Saca los bytes de la primera imagen que venga en la respuesta."""
    if isinstance(nodo, dict):
        for k in ("inlineData", "inline_data"):
            d = nodo.get(k)
            if isinstance(d, dict) and d.get("data") and \
                    str(d.get("mimeType") or d.get("mime_type") or "image").startswith("image"):
                try:
                    return base64.b64decode(d["data"])
                except Exception:
                    pass
        for v in nodo.values():
            b = _buscar_imagen(v)
            if b:
                return b
    elif isinstance(nodo, list):
        for v in nodo:
            b = _buscar_imagen(v)
            if b:
                return b
    return None


def modelos_de_imagen():
    """Qué modelos de imagen ofrece esta clave. Para que un fallo se explique solo."""
    try:
        r = requests.get(f"{BASE}/models", headers={"x-goog-api-key": _clave()},
                         params={"pageSize": 200}, timeout=60)
        nombres = [m.get("name", "").split("/")[-1] for m in r.json().get("models", [])]
        hay = [n for n in nombres if "image" in n or "imagen" in n]
        return ", ".join(hay) or f"ninguno con 'image' en el nombre (de {len(nombres)})"
    except Exception as e:
        return f"no se pudo consultar la lista ({type(e).__name__})"


def imagen(prompt, referencia=None):
    """Genera una imagen. Devuelve (bytes, None) o (None, qué dijo cada modelo)."""
    global _img_elegido
    partes = [{"text": prompt}]
    if referencia:
        partes.append({"inline_data": {"mime_type": "image/jpeg",
                                       "data": base64.b64encode(referencia).decode()}})
    cuerpo = {"contents": [{"role": "user", "parts": partes}],
              "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
    orden = ([_img_elegido] if _img_elegido else []) + \
            [m for m in IMG_MODELOS if m != _img_elegido and m not in _descartados]
    dichos = []
    for modelo in orden:
        try:
            data = _post(f"{BASE}/models/{modelo}:generateContent", cuerpo)
        except GeminiError as e:
            if _sin_cupo(e):
                _descartados.add(modelo)
            dichos.append(f"{modelo}: {str(e)[:150]}")
            continue
        if data is None:
            _descartados.add(modelo)
            dichos.append(f"{modelo}: no existe para esta clave (404)")
            continue
        b = _buscar_imagen(data)
        if b and len(b) > 20000:
            _img_elegido = modelo
            return b, None
        dichos.append(f"{modelo}: contestó sin imagen"
                      + (f" ({len(b)} bytes)" if b else ""))
    return None, dichos
