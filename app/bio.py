"""Mirar cómo está la biografía de Allie y si declara que es un personaje de IA.

Quien llega al perfil desde explorar no lee ningún pie: ve la foto, el
nombre y la biografía. Si la declaración solo está en los pies, esa persona
no se entera. El reglamento habla de la primera exposición, y para mucha
gente la primera exposición es el perfil.

Solo LEE. La API de Instagram no deja cambiar la biografía: eso se hace a
mano desde la aplicación, así que esto escribe lo que habría que poner y
Teresa lo copia.
"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
BASE = Path(__file__).resolve().parent.parent

import main as bot  # noqa: E402
from ig import Instagram  # noqa: E402

INFORME = BASE / "publicar" / "biografia.md"

SEÑALES = ("ia", "a.i", "ai ", "inteligencia artificial", "virtual",
           "generad", "ficticia", "ficción", "no soy real", "personaje")


def main():
    INFORME.parent.mkdir(exist_ok=True)
    token, ig_id, page_id = bot.credenciales()
    ig = Instagram(token=token, ig_id=ig_id, page_id=page_id)
    d = ig._req("GET", ig.yo,
                fields="username,name,biography,followers_count,website")
    bio = (d.get("biography") or "").strip()
    nombre = (d.get("name") or "").strip()
    junto = f"{nombre} {bio}".lower()
    declara = [s for s in SEÑALES if s in junto]

    lineas = ["# La biografía de Allie", "",
              f"- usuario: **@{d.get('username')}**",
              f"- nombre: **{nombre or '(vacío)'}**",
              f"- seguidores: {d.get('followers_count')}",
              "", "## Biografía actual", "", "```", bio or "(vacía)", "```", "",
              f"**¿Declara que es un personaje de IA?** "
              f"{'parece que sí · ' + ', '.join(declara) if declara else '**NO**'}", ""]
    if not declara:
        lineas += [
            "Quien llega al perfil desde explorar no lee ningún pie: ve la foto, "
            "el nombre y la biografía. Conviene que lo diga aquí también.", "",
            "Propuesta para pegar (la primera línea es la que importa):", "",
            "```",
            "🤖 Personaje creado con IA · no soy una persona real",
            bio or "Madrid · otoño, café y mis gatos",
            "```", ""]
    INFORME.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        INFORME.parent.mkdir(exist_ok=True)
        INFORME.write_text("# La biografía de Allie\n\nNo se pudo leer:\n\n```\n"
                           + traceback.format_exc()[-2000:] + "\n```\n", encoding="utf-8")
        raise
