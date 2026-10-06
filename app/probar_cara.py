"""¿El único modelo que queda gratis usa de verdad la foto de Allie, o la ignora?

La prueba es simple: la misma escena, la misma foto de referencia, dos semillas
distintas. Si la cara cambia de una a otra, la referencia no se está usando y
el modelo está inventando una mujer cada vez.

Deja las imágenes en videos/prueba/ junto a la foto de referencia, para poder
compararlas mirándolas, que es la única forma de saberlo.
"""
from pathlib import Path
from urllib.parse import quote
import os

import requests

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "videos" / "prueba"
REFERENCIA = "https://i.postimg.cc/023T5BJX/IMG-20261001-215255.jpg"
ESCENA = ("The same young woman from the reference photo, identical face and hair, "
          "sitting at a cafe terrace in Madrid with a coffee, upper-body shot, "
          "soft morning light, calm closed mouth, photorealistic")

SALIDA.mkdir(parents=True, exist_ok=True)

r = requests.get(REFERENCIA, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
(SALIDA / "0-REFERENCIA.jpg").write_bytes(r.content)
print(f"referencia: {len(r.content)//1024} KB", flush=True)

clave = os.environ.get("POLLINATIONS_KEY", "")
for semilla in (11, 2222):
    pars = {"model": "sana", "width": 768, "height": 960, "seed": semilla,
            "nologo": "true", "image": REFERENCIA}
    cab = {"User-Agent": "Mozilla/5.0"}
    if clave:
        cab["Authorization"] = f"Bearer {clave}"
    r = requests.get(f"https://image.pollinations.ai/prompt/{quote(ESCENA)}",
                     params=pars, headers=cab, timeout=300)
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
        (SALIDA / f"sana-semilla-{semilla}.jpg").write_bytes(r.content)
        print(f"semilla {semilla}: {len(r.content)//1024} KB", flush=True)
    else:
        print(f"semilla {semilla}: HTTP {r.status_code} · {r.text[:150]}", flush=True)
