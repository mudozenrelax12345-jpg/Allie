"""¿Puede Allie publicar sola, sin pasar por Metricool?

POR QUÉ. El plan gratuito de Metricool da 20 publicaciones por mes natural.
El 16 de octubre ya iban 17 y quedaban quince días: publicar a diario era
imposible por esa única razón, teniendo 71 fotos listas en el banco.

La API de Instagram no tiene ese límite (Meta permite 25 publicaciones cada
24 horas, que es cinco veces lo que haría falta). Y el token ya existe: es el
mismo con el que el bot contesta comentarios desde hace semanas. La pregunta
es si tiene el permiso de PUBLICAR, que es distinto del de responder.

QUÉ HACE, Y QUÉ NO. Pregunta a Meta qué permisos tiene el token y, si parece
que puede, hace la primera mitad de una publicación de verdad: crea el
contenedor con el vídeo. NO llama a media_publish, así que no aparece nada en
la cuenta. Un contenedor sin publicar caduca solo en 24 horas.

Hacer media mitad es lo único que responde la pregunta de verdad: la lista de
permisos puede decir que sí y luego fallar la llamada por la configuración de
la app, y eso hay que saberlo antes de montar nada encima.
"""
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
BASE = Path(__file__).resolve().parent.parent

import main as bot  # noqa: E402
from ig import IGError, Instagram  # noqa: E402

INFORME = BASE / "publicar" / "informe.md"

# Los permisos que hacen falta para publicar. Los nombres han cambiado con
# las versiones de la API, así que se buscan los dos.
PUBLICAR = ("instagram_business_content_publish", "instagram_content_publish")


def main():
    INFORME.parent.mkdir(exist_ok=True)
    lineas = ["# ¿Puede Allie publicar sin Metricool?", ""]

    def guardar():
        INFORME.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    try:
        token, ig_id, page_id = bot.credenciales()
    except Exception as e:  # noqa: BLE001
        lineas += [f"No se pudieron leer las credenciales: {e}"]
        guardar()
        sys.exit(1)
    if not token:
        lineas += ["No hay token guardado."]
        guardar()
        sys.exit(1)

    ig = Instagram(token=token, ig_id=ig_id, page_id=page_id)

    # 1 · Qué permisos tiene.
    lineas += ["## Permisos del token", ""]
    concedidos = set()
    try:
        d = ig._req("GET", "me/permissions")
        for p in d.get("data", []):
            if p.get("status") == "granted":
                concedidos.add(p.get("permission"))
        for p in sorted(concedidos):
            lineas.append(f"- {p}")
    except Exception as e:  # noqa: BLE001
        lineas.append(f"No pude leer los permisos: {e}")

    puede = [p for p in PUBLICAR if p in concedidos]
    lineas += ["", f"**Permiso de publicar: {'SÍ · ' + puede[0] if puede else 'no aparece'}**", ""]

    # 2 · La prueba de verdad: crear el contenedor y NO publicarlo.
    lineas += ["## Prueba real (crear el contenedor, sin publicar)", ""]
    mp4 = None
    try:
        ultimo = json.loads((BASE / "videos" / "ultimo.json").read_text(encoding="utf-8"))
        nombre = ultimo.get("archivo")
        if nombre and (BASE / "videos" / nombre).exists():
            mp4 = ("https://raw.githubusercontent.com/mudozenrelax12345-jpg/Allie/"
                   f"main/videos/{nombre}")
    except Exception as e:  # noqa: BLE001
        lineas.append(f"No pude saber cuál es el último vídeo: {e}")

    if not mp4:
        lineas += ["No hay vídeo con el que probar.", ""]
        guardar()
        sys.exit(1)

    lineas += [f"Vídeo: `{mp4}`", ""]
    try:
        r = ig._req("POST", f"{ig.yo}/media", media_type="REELS", video_url=mp4,
                    caption="(prueba que no se publica)", share_to_feed="true")
        contenedor = r.get("id")
        lineas += [f"- ✅ **Contenedor creado**: `{contenedor}`",
                   "- No se ha llamado a media_publish, así que **no hay nada en la "
                   "cuenta**. El contenedor caduca solo en 24 h.", ""]
        # Instagram procesa el vídeo en segundo plano; mirar el estado da la
        # confirmación definitiva de que el vídeo le vale.
        for intento in range(6):
            time.sleep(10)
            try:
                e = ig._req("GET", contenedor, fields="status_code,status")
            except Exception:  # noqa: BLE001
                break
            cod = e.get("status_code")
            lineas.append(f"  - a los {(intento + 1) * 10}s: `{cod}`")
            if cod in ("FINISHED", "ERROR", "EXPIRED"):
                if cod == "ERROR":
                    lineas.append(f"  - detalle: {str(e.get('status'))[:300]}")
                break
        lineas += ["", "**Conclusión: Allie puede publicar sin Metricool.**", ""]
    except IGError as e:
        lineas += [f"- ❌ No se pudo crear el contenedor: `{e}`", "",
                   "Eso significa que falta el permiso o la app no está "
                   "configurada para publicar. Se pide en el panel de "
                   "desarrolladores de Meta y es gratis.", ""]
    except Exception as e:  # noqa: BLE001
        lineas += [f"- ❌ Reventó: `{type(e).__name__}: {e}`", "", "```",
                   traceback.format_exc()[-1200:], "```", ""]

    guardar()
    print("\n".join(lineas), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        INFORME.parent.mkdir(exist_ok=True)
        INFORME.write_text("# ¿Puede Allie publicar sin Metricool?\n\nReventó:\n\n```\n"
                           + traceback.format_exc()[-2500:] + "\n```\n", encoding="utf-8")
        raise
