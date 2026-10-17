"""Lo que se ejecuta DENTRO de la GPU gratuita de Kaggle.

POR QUÉ EXISTE. El 17 de octubre se cerraron todas las puertas a la vez:
Cloudflare sin cupo, Gemini con «limit: 0» para imágenes, NVIDIA pidiendo
verificar la cuenta, Leonardo sin API en el plan gratis, Pollinations con
saldo cero y los espacios de Hugging Face rotos. Un día entero sin poder
generar una foto.

El error era la pregunta. Llevaba el día buscando quién regala IMÁGENES,
que las raciona todo el mundo, cuando lo que se regala por horas es la
MÁQUINA: Kaggle da 30 horas semanales de GPU a cualquiera con un teléfono
verificado. Treinta horas, a un minuto por imagen, son más de mil imágenes
a la semana sin contar ninguna.

Y la licencia deja de ser un problema. Qwen-Image-Edit es Apache 2.0: si lo
corremos nosotros, lo que salga se le puede cobrar a una marca sin el
asterisco que arrastraba FLUX.1 Kontext dev, que es de uso no comercial.

CÓMO FUNCIONA. Kaggle ejecuta este fichero solo, sin nadie delante. Así que
se clona el repositorio él mismo (es público, no hace falta clave), lee la
lista de encargos, genera cada uno y deja las imágenes en /kaggle/working.
Después, el trabajo de GitHub se las baja y las guarda en el repositorio.

NINGUNA CLAVE VIAJA HASTA AQUÍ. Este fichero se sube a un servidor de
terceros, así que no lleva tokens: lo único que hace es leer de un
repositorio público y escribir ficheros en su propia carpeta de trabajo.

EL PRIMER DÍA VA A FALLAR. Siempre falla. Por eso lo que más importa de
este fichero no es que genere, sino que CUENTE: cada paso deja su línea en
el informe, de modo que si se rompe a la tercera hora sepamos exactamente
en qué se rompió, sin tener que adivinar.
"""
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

TRABAJO = Path("/kaggle/working")
REPO = "https://github.com/mudozenrelax12345-jpg/Allie.git"
CARPETA = Path("/kaggle/working/allie")

# El modelo en 4 bits: el completo no cabe en los 16 GB de la tarjeta.
MODELO = os.environ.get("MODELO_QWEN", "ovedrive/qwen-image-edit-4bit")
PASOS = int(os.environ.get("PASOS", "20"))

PARTE = []


def di(m):
    linea = f"{datetime.now(timezone.utc):%H:%M:%S} · {m}"
    print(linea, flush=True)
    PARTE.append(linea)
    try:
        (TRABAJO / "parte.txt").write_text("\n".join(PARTE) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def correr(orden, titulo):
    di(f"{titulo}…")
    t0 = time.time()
    r = subprocess.run(orden, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        di(f"  MAL ({round(time.time() - t0)}s): {(r.stderr or r.stdout)[-600:]}")
        return False
    di(f"  bien ({round(time.time() - t0)}s)")
    return True


def guardar(resultados):
    (TRABAJO / "informe.json").write_text(json.dumps({
        "cuando": datetime.now(timezone.utc).isoformat(),
        "modelo": MODELO, "pasos": PASOS, "encargos": resultados,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    di(f"Arranco. Modelo: {MODELO}")

    # 1 · Qué máquina nos ha tocado. Si no hay GPU no merece la pena seguir:
    #     en procesador esto tardaría horas y la sesión se corta a las doce.
    try:
        import torch
        hay_gpu = torch.cuda.is_available()
        di(f"torch {torch.__version__} · GPU: "
           f"{torch.cuda.get_device_name(0) if hay_gpu else 'NO HAY'}")
        if not hay_gpu:
            di("Sin GPU no sigo: en procesador no da tiempo en una sesión.")
            guardar([{"error": "sin GPU"}])
            return
    except Exception as e:  # noqa: BLE001
        di(f"torch no se puede importar: {e}")
        guardar([{"error": f"sin torch: {e}"}])
        return

    # 2 · El repositorio, para leer los encargos y la foto de Allie.
    if not CARPETA.exists():
        if not correr(f"git clone --depth 1 {REPO} {CARPETA}", "Clono el repositorio"):
            guardar([{"error": "no se pudo clonar"}])
            return

    pendientes = CARPETA / "encargos" / "pendientes.json"
    if not pendientes.exists():
        di("No hay encargos/pendientes.json: no hay nada que generar.")
        guardar([{"error": "sin lista de encargos"}])
        return
    encargos = json.loads(pendientes.read_text(encoding="utf-8")).get("encargos") or []
    di(f"{len(encargos)} encargos en la lista")
    if not encargos:
        guardar([])
        return

    # 3 · Las bibliotecas. Kaggle trae torch puesto; lo demás no siempre.
    correr(f"{sys.executable} -m pip install -q --upgrade "
           f"diffusers transformers accelerate bitsandbytes safetensors pillow",
           "Instalo las bibliotecas")

    # 4 · El modelo. Son varios gigas: esto es lo que más tarda, y por eso
    #     interesa generar MUCHAS imágenes por sesión y no una suelta.
    di("Cargo el modelo (esto son varios minutos)…")
    t0 = time.time()
    try:
        import torch
        from diffusers import QwenImageEditPipeline
        tuberia = QwenImageEditPipeline.from_pretrained(
            MODELO, torch_dtype=torch.bfloat16)
        tuberia.to("cuda")
        tuberia.set_progress_bar_config(disable=True)
    except Exception:  # noqa: BLE001
        di("No se pudo cargar el modelo:\n" + traceback.format_exc()[-1500:])
        guardar([{"error": "no cargó el modelo"}])
        return
    di(f"  modelo listo en {round(time.time() - t0)}s")

    # 5 · A generar.
    from io import BytesIO

    import requests
    from PIL import Image

    resultados = []
    for i, e in enumerate(encargos, 1):
        nombre = e.get("nombre") or f"encargo-{i}"
        apunte = {"nombre": nombre}
        try:
            r = requests.get(e["referencia"], timeout=120)
            referencia = Image.open(BytesIO(r.content)).convert("RGB")
        except Exception as ex:  # noqa: BLE001
            apunte["error"] = f"no se pudo bajar la referencia: {ex}"
            di(f"{nombre}: {apunte['error']}")
            resultados.append(apunte)
            guardar(resultados)
            continue

        t0 = time.time()
        try:
            salida = tuberia(image=referencia, prompt=e["escena"],
                             num_inference_steps=PASOS,
                             true_cfg_scale=4.0).images[0]
            f = TRABAJO / f"{nombre}.jpg"
            salida.save(f, "JPEG", quality=94)
            apunte.update({"archivo": f.name, "segundos": round(time.time() - t0, 1)})
            di(f"{nombre}: hecha en {apunte['segundos']}s")
        except Exception:  # noqa: BLE001
            apunte["error"] = traceback.format_exc()[-800:]
            di(f"{nombre}: MAL\n{apunte['error']}")
        resultados.append(apunte)
        guardar(resultados)

    hechas = sum(1 for r in resultados if r.get("archivo"))
    di(f"TERMINADO · {hechas} de {len(encargos)}")
    guardar(resultados)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        di("REVENTÓ:\n" + traceback.format_exc()[-2000:])
        raise
