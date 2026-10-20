"""De qué vídeo estamos hablando.

El canal va a tener muchos vídeos y la maquinaria es la misma para todos. Lo
único que cambia es la carpeta de configuración:

  videos/01-hertz/material.yml   qué clips descargar
  videos/01-hertz/tarjetas.yml   qué texto sale en pantalla
  videos/01-hertz/montaje.yml    qué se ve en cada párrafo

Se elige con la variable VIDEO. Si no se dice nada, el primero por orden.
"""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
VIDEOS = BASE / "videos"


def cual():
    pedido = os.environ.get("VIDEO", "").strip()
    if pedido and (VIDEOS / pedido).is_dir():
        return pedido
    carpetas = sorted(p.name for p in VIDEOS.iterdir() if p.is_dir()) if VIDEOS.is_dir() else []
    if pedido and not carpetas:
        return pedido
    return carpetas[0] if carpetas else "01-hertz"


def ruta(nombre):
    """videos/<id>/<nombre>, con la raíz del repo como respaldo."""
    f = VIDEOS / cual() / nombre
    return f if f.exists() else BASE / nombre


def guion():
    pedido = os.environ.get("GUION", "").strip()
    if pedido:
        return Path(pedido)
    posibles = sorted((BASE / "guiones").glob(f"{cual().split('-')[0]}-*.md"))
    return posibles[0] if posibles else None
