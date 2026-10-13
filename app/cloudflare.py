"""Generar fotos de Allie en Cloudflare Workers AI, que no gasta cuota de HF.

POR QUÉ. Hugging Face lleva desde el 11 de octubre sin darnos una sola
generación: nueve intentos repartidos en tres días, todos «sin cuota». Con
eso la cuenta se quedó sin poder publicar nada nuevo. Cloudflare da 10.000
«neuronas» al día gratis, se reinicia a las 00:00 UTC —hora fija, no una
ventana que se mueve— y sus condiciones no limitan el uso comercial.

QUÉ MODELO. flux-2-klein-4b, que hace edición con hasta cuatro imágenes de
referencia, que es justo lo que Allie necesita: su foto más una escena.
Cuesta unas 110 neuronas por imagen de 1024×1024, o sea unas NOVENTA fotos
al día. El hermano mayor, klein-9b, da mejor calidad pero cuesta 1.364
neuronas por megapíxel: siete fotos al día, apenas mejor que lo que
teníamos. Por eso el pequeño va primero y el grande queda para cuando haga
falta una foto que importe de verdad.

DETALLES QUE CUESTAN UNA EJECUCIÓN SI SE PASAN POR ALTO:
  · La entrada es multipart/form-data, no JSON, incluso sin imágenes.
  · Las imágenes de referencia se llaman input_image_0 … input_image_3.
  · Tienen que medir MENOS de 512×512. Nuestra referencia es mayor, así que
    se encoge antes de enviarla.
  · No hay que poner la cabecera Content-Type a mano: sin el «boundary» que
    añade requests, el servidor no puede leer el cuerpo.
  · La imagen vuelve en base64 dentro de result.image.

Credenciales: CF_ACCOUNT_ID y CF_API_TOKEN. Sin ellas este camino se salta
en silencio y se sigue por Hugging Face, así que añadirlas es lo único que
hace falta para encenderlo.
"""
import base64
import os
import time
from io import BytesIO

import requests
from PIL import Image

BASE = "https://api.cloudflare.com/client/v4/accounts"

# El pequeño primero: trece veces más barato que el grande y hace lo mismo.
MODELOS = [m.strip() for m in os.environ.get(
    "CF_MODELOS",
    "@cf/black-forest-labs/flux-2-klein-4b,"
    "@cf/black-forest-labs/flux-2-klein-9b").split(",") if m.strip()]

ANCHO = int(float(os.environ.get("CF_ANCHO", "1024") or 1024))
ALTO = int(float(os.environ.get("CF_ALTO", "1280") or 1280))
LADO_REFERENCIA = 480      # por debajo del máximo de 512 que exige el modelo


class SinCredenciales(RuntimeError):
    pass


# Los nombres buenos van primero, pero se aceptan las variantes razonables:
# equivocarse al teclear el nombre de un secreto da «no hay credenciales», que
# es el peor aviso posible, porque parece que no lo has puesto.
NOMBRES_CUENTA = ["CF_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT",
                  "CF_ID", "CF_CUENTA"]
NOMBRES_FICHA = ["CF_API_TOKEN", "CLOUDFLARE_API_TOKEN", "CF_TOKEN",
                 "CF_API_KEY", "CLOUDFLARE_TOKEN", "CF_FICHA"]


def _primero(nombres):
    """(valor, de qué variable salió) o (None, None)."""
    for n in nombres:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v, n
    return None, None


def credenciales():
    cuenta, _ = _primero(NOMBRES_CUENTA)
    ficha, _ = _primero(NOMBRES_FICHA)
    return (cuenta, ficha) if cuenta and ficha else (None, None)


def diagnostico():
    """Qué hay y qué falta, SIN enseñar ningún valor."""
    cuenta, de_cuenta = _primero(NOMBRES_CUENTA)
    ficha, de_ficha = _primero(NOMBRES_FICHA)
    return {
        "cuenta": bool(cuenta), "cuenta_en": de_cuenta,
        "cuenta_largo": len(cuenta or ""),
        "ficha": bool(ficha), "ficha_en": de_ficha,
        "ficha_largo": len(ficha or ""),
    }


def hay():
    return all(credenciales())


def _referencia_pequena(datos):
    """La referencia, por debajo de 512×512, que es lo que el modelo admite.

    Se encoge manteniendo la proporción y se manda en JPEG de calidad alta:
    la cara tiene que seguir siendo reconocible, que es todo el objetivo.
    """
    im = Image.open(BytesIO(datos)).convert("RGB")
    im.thumbnail((LADO_REFERENCIA, LADO_REFERENCIA), Image.LANCZOS)
    b = BytesIO()
    im.save(b, "JPEG", quality=95)
    return b.getvalue()


def generar(referencia, orden, modelos=None):
    """(bytes, segundos, modelo) o (None, 0, motivos).

    `referencia` son los bytes de la foto de Allie; `orden`, el texto.
    """
    cuenta, ficha = credenciales()
    if not cuenta:
        raise SinCredenciales(
            "Faltan CF_ACCOUNT_ID y CF_API_TOKEN; me salto Cloudflare")

    pequena = _referencia_pequena(referencia)
    dichos = []
    for modelo in (modelos or MODELOS):
        t0 = time.time()
        try:
            r = requests.post(
                f"{BASE}/{cuenta}/ai/run/{modelo}",
                headers={"Authorization": f"Bearer {ficha}"},
                # Sin Content-Type a mano: requests le pone el boundary.
                files={"input_image_0": ("allie.jpg", pequena, "image/jpeg")},
                data={"prompt": orden, "width": str(ANCHO), "height": str(ALTO)},
                timeout=240)
        except Exception as e:  # noqa: BLE001
            dichos.append(f"{modelo}: {type(e).__name__}: {str(e)[:160]}")
            continue

        if r.status_code != 200:
            dichos.append(f"{modelo}: HTTP {r.status_code} · {r.text[:200]}")
            continue
        try:
            cuerpo = r.json()
        except Exception:  # noqa: BLE001
            dichos.append(f"{modelo}: contestó algo que no es JSON · {r.text[:120]}")
            continue
        if not cuerpo.get("success"):
            dichos.append(f"{modelo}: {str(cuerpo.get('errors'))[:200]}")
            continue

        b64 = (cuerpo.get("result") or {}).get("image")
        if not b64:
            dichos.append(f"{modelo}: contestó sin imagen · {str(cuerpo)[:150]}")
            continue
        try:
            datos = base64.b64decode(b64)
            im = Image.open(BytesIO(datos)).convert("RGB")
        except Exception as e:  # noqa: BLE001
            dichos.append(f"{modelo}: la imagen no se puede abrir · {e}")
            continue

        salida = BytesIO()
        im.save(salida, "JPEG", quality=94)
        return salida.getvalue(), round(time.time() - t0, 1), modelo

    return None, 0, dichos
