"""Cuaderno mínimo para saber si Kaggle nos ejecuta algo, sí o no.

El 17 de octubre la primera tanda de verdad se quedó en cola noventa
minutos y nunca arrancó. Con una tanda grande no hay forma de distinguir
entre «Kaggle va lleno», «esta cuenta no tiene GPU» y «hay algo mal en
nuestro cuaderno»: las tres cosas se ven igual desde fuera.

Esto no pide GPU ni internet. Si ESTO tampoco arranca, el problema es la
cuenta. Si arranca en dos minutos, el problema es el permiso de GPU, que
en Kaggle va atado a verificar el teléfono.

Una pregunta por vez, que es como se averigua algo.
"""
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

TRABAJO = Path("/kaggle/working")

lineas = [
    f"hola desde Kaggle · {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC",
    f"python {platform.python_version()} · {platform.platform()}",
    f"procesadores: {os.cpu_count()}",
]

try:
    import torch
    lineas.append(f"torch {torch.__version__}")
    lineas.append(f"GPU disponible: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        lineas.append(f"tarjeta: {torch.cuda.get_device_name(0)}")
except Exception as e:  # noqa: BLE001
    lineas.append(f"torch no se puede importar: {e}")

texto = "\n".join(lineas)
print(texto, flush=True)
(TRABAJO / "hola.txt").write_text(texto + "\n", encoding="utf-8")
