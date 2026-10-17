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
import json
import os
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

BASE = "https://api.cloudflare.com/client/v4/accounts"

# ------------------------------------------------------------- contabilidad
#
# El 17 de octubre el cupo diario estaba agotado a las 04:35 UTC sin que
# hubiera corrido nada desde las 21:33 del día anterior, y no había forma
# de saber quién se lo había comido. Teorías había varias; datos, ninguno.
#
# Desde aquí cada llamada deja una línea: qué trabajo la pidió, qué modelo,
# cuánto tardó y si salió. Ni el texto de la orden ni la clave: sólo lo que
# hace falta para sumar el día y señalar al culpable.
#
# Las neuronas son estimaciones MEDIDAS por nosotros, no cifras oficiales de
# Cloudflare. Sirven para comparar entre sí, no para facturar.
NEURONAS = {
    "@cf/black-forest-labs/flux-2-klein-4b": 110,
    "@cf/black-forest-labs/flux-2-klein-9b": 1430,
}
NEURONAS_TEXTO = 3
GASTO = Path(__file__).resolve().parent.parent / "estado" / "gasto-cloudflare.jsonl"


# El freno. Lo que pasó el 16 de octubre: regeneré el muestrario DOS veces
# con el modelo grande, dieciséis imágenes de 1.430 neuronas, casi veintitrés
# mil. Más de dos días de cupo en veinte minutos, y a la mañana siguiente no
# había con qué atender a un cliente ni con qué probar nada.
#
# Se mira la ventana de las últimas 24 HORAS, no el día natural: es la
# hipótesis que encaja con lo observado, y además es la más prudente de las
# dos. Si Cloudflare cuenta por día natural, este freno sobra algunas horas;
# si cuenta por ventana, evita exactamente el agujero en el que caímos.
TECHO_NEURONAS = int(float(os.environ.get("CF_TECHO_NEURONAS") or 9000))


class SinCupo(RuntimeError):
    pass


def gastado_24h():
    """Neuronas apuntadas en las últimas 24 horas. 0 si no hay registro."""
    if not GASTO.exists():
        return 0
    desde = datetime.now(timezone.utc).timestamp() - 24 * 3600
    total = 0
    try:
        for linea in GASTO.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            try:
                a = json.loads(linea)
                cuando = datetime.fromisoformat(a["cuando"]).timestamp()
            except Exception:  # noqa: BLE001
                continue
            if cuando >= desde:
                total += int(a.get("neuronas") or 0)
    except Exception:  # noqa: BLE001
        return 0
    return total


def _apuntar(modelo, ok, segundos, clase="imagen"):
    try:
        GASTO.parent.mkdir(parents=True, exist_ok=True)
        with GASTO.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "cuando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "quien": Path(sys.argv[0]).stem or "?",
                "modelo": modelo,
                "clase": clase,
                "ok": bool(ok),
                "segundos": segundos,
                "neuronas": (NEURONAS.get(modelo, 110) if clase == "imagen"
                             else NEURONAS_TEXTO) if ok else 0,
            }, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass          # contar nunca puede ser el motivo de que algo falle

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


MAX_IMAGENES = 4           # input_image_0 … input_image_3, y no hay más


def generar(referencia, orden, modelos=None, extras=None):
    """(bytes, segundos, modelo) o (None, 0, motivos).

    `referencia` son los bytes de la foto de Allie; `orden`, el texto.

    `extras` son OTRAS imágenes que entran en la escena, hasta tres. Esto es
    lo que hace posible el encargo de una marca: la foto del producto del
    cliente va de extra, y el modelo tiene que respetar su forma y su color
    en vez de inventarse un producto parecido. Sin esto sólo se puede generar
    «un tarro blanco cualquiera», que a una marca no le sirve de nada.
    """
    cuenta, ficha = credenciales()
    if not cuenta:
        raise SinCredenciales(
            "Faltan CF_ACCOUNT_ID y CF_API_TOKEN; me salto Cloudflare")

    gastado = gastado_24h()
    if gastado >= TECHO_NEURONAS:
        raise SinCupo(
            f"Freno propio: van {gastado} neuronas en 24 h, el techo está en "
            f"{TECHO_NEURONAS}. No pido más para no dejar sin cupo lo de mañana.")

    imagenes = {"input_image_0": ("allie.jpg", _referencia_pequena(referencia),
                                  "image/jpeg")}
    for i, extra in enumerate(extras or [], start=1):
        if i >= MAX_IMAGENES:
            break
        imagenes[f"input_image_{i}"] = (
            f"extra{i}.jpg", _referencia_pequena(extra), "image/jpeg")
    dichos = []
    for modelo in (modelos or MODELOS):
        t0 = time.time()
        try:
            r = requests.post(
                f"{BASE}/{cuenta}/ai/run/{modelo}",
                headers={"Authorization": f"Bearer {ficha}"},
                # Sin Content-Type a mano: requests le pone el boundary.
                files=imagenes,
                data={"prompt": orden, "width": str(ANCHO), "height": str(ALTO)},
                timeout=240)
        except Exception as e:  # noqa: BLE001
            dichos.append(f"{modelo}: {type(e).__name__}: {str(e)[:160]}")
            _apuntar(modelo, False, round(time.time() - t0, 1))
            continue

        if r.status_code != 200:
            dichos.append(f"{modelo}: HTTP {r.status_code} · {r.text[:200]}")
            _apuntar(modelo, False, round(time.time() - t0, 1))
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
        segundos = round(time.time() - t0, 1)
        _apuntar(modelo, True, segundos)
        return salida.getvalue(), segundos, modelo

    return None, 0, dichos


# --------------------------------------------------------------- texto
#
# Cloudflare no solo genera imágenes: con las mismas credenciales y el mismo
# cupo de 10.000 neuronas diarias hay modelos de texto. Esto existe porque el
# 16 de octubre Gemini se quedó sin cuota a media mañana y con él se cayó
# todo: las escenas, el guion y el texto del post. Un segundo proveedor por
# el que ya pagamos cero convierte eso en un contratiempo en vez de un día
# sin publicar.
#
# Los identificadores de modelo cambian, así que se prueban varios en orden y
# un 404 pasa al siguiente en vez de tumbar la llamada.
MODELOS_TEXTO = [m.strip() for m in os.environ.get(
    "CF_MODELOS_TEXTO",
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast,"
    "@cf/meta/llama-3.1-8b-instruct-fp8,"
    "@cf/meta/llama-3.1-8b-instruct").split(",") if m.strip()]


def texto(prompt, modelos=None):
    """El texto que conteste el primer modelo que funcione, o None."""
    cuenta, ficha = credenciales()
    if not cuenta:
        return None, ["sin credenciales de Cloudflare"]
    dichos = []
    for modelo in (modelos or MODELOS_TEXTO):
        try:
            r = requests.post(
                f"{BASE}/{cuenta}/ai/run/{modelo}",
                headers={"Authorization": f"Bearer {ficha}",
                         "Content-Type": "application/json"},
                json={"messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 1200},
                timeout=180)
        except Exception as e:  # noqa: BLE001
            dichos.append(f"{modelo}: {type(e).__name__}: {str(e)[:120]}")
            continue
        if r.status_code != 200:
            dichos.append(f"{modelo}: HTTP {r.status_code} · {r.text[:150]}")
            _apuntar(modelo, False, 0, "texto")
            continue
        try:
            cuerpo = r.json()
        except Exception:  # noqa: BLE001
            dichos.append(f"{modelo}: no contestó JSON")
            continue
        if not cuerpo.get("success"):
            dichos.append(f"{modelo}: {str(cuerpo.get('errors'))[:150]}")
            continue
        res = cuerpo.get("result") or {}
        t = res.get("response") or res.get("output") or ""
        if isinstance(t, list):
            t = " ".join(str(x) for x in t)
        if not str(t).strip():
            dichos.append(f"{modelo}: contestó vacío")
            continue
        _apuntar(modelo, True, 0, "texto")
        return str(t), [modelo]
    return None, dichos
