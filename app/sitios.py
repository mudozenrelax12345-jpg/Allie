"""La ubicación de la publicación: meter el post en el feed de un sitio.

POR QUÉ. Etiquetar la cuenta de una cafetería le llega a ella y, con suerte,
lo reseñea. Etiquetar el LUGAR hace otra cosa distinta y para captar gente
nueva vale más: la publicación entra en el feed de ese sitio, que es donde
mira la gente de Madrid que está buscando dónde ir. Y no depende de acertar
ningún arroba: un identificador de lugar o existe o no existe.

CÓMO, y POR QUÉ NO SE PUEDE (comprobado el 19 de octubre). Instagram acepta
`location_id` al crear el contenedor, pero el identificador es de una PÁGINA
de Facebook y hay que buscarlo con /pages/search. Dos muros:

  1. Nuestro token es el de la PÁGINA, no el de usuario: main.credenciales()
     lo deriva así a propósito porque el de página no caduca. /pages/search
     pide uno de usuario, y /me/permissions ni siquiera existe para una
     página («nonexisting field»).
  2. Y aunque fuera de usuario con pages_read_engagement, buscar páginas que
     no son tuyas exige la función «Page Public Content Access», que Meta
     concede solo pasando revisión de la aplicación.

O sea que no es cuestión de marcar una casilla. Esto se queda escrito y se
sigue intentando sin romper nada, por si algún día cambia; la ubicación,
mientras tanto, se pone a mano editando la publicación en la app.

Lo encontrado se guarda en contenido/sitios.json, porque el identificador
de un sitio no cambia y no tiene sentido preguntarlo cada vez. Un sitio que
no aparezca se queda sin ubicación y la publicación sale igual: nunca al
revés.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
BASE = Path(__file__).resolve().parent.parent
FICHERO = BASE / "contenido" / "sitios.json"

# El centro de Madrid, para que la búsqueda no devuelva un sitio homónimo
# de Buenos Aires. Puerta del Sol.
CENTRO = "40.4169,-3.7035"
RADIO = 15000      # metros


def guardados():
    try:
        return json.loads(FICHERO.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def apuntar(nombre, ficha):
    d = guardados()
    d[nombre] = ficha
    FICHERO.parent.mkdir(parents=True, exist_ok=True)
    FICHERO.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def buscar(ig, nombre, usar_cache=True):
    """(location_id, detalle). Devuelve (None, motivo) si no se encuentra."""
    if usar_cache:
        ficha = guardados().get(nombre)
        if ficha:
            return ficha.get("id"), f"de la caché · {ficha.get('nombre')}"
    try:
        r = ig._req("GET", "pages/search", q=nombre, type="place",
                    center=CENTRO, distance=RADIO,
                    fields="id,name,location,link")
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:200]}"
    datos = (r or {}).get("data") or []
    if not datos:
        return None, "sin resultados"
    # El primero que esté en Madrid; si ninguno lo dice, el primero a secas.
    elegido = next((p for p in datos
                    if "madrid" in str(p.get("location", {}).get("city", "")).lower()),
                   datos[0])
    apuntar(nombre, {"id": elegido.get("id"), "nombre": elegido.get("name"),
                     "ciudad": (elegido.get("location") or {}).get("city")})
    return elegido.get("id"), f"{elegido.get('name')} · {(elegido.get('location') or {}).get('city')}"


if __name__ == "__main__":
    import main as bot
    from ig import Instagram
    token, ig_id, page_id = bot.credenciales()
    ig = Instagram(token=token, ig_id=ig_id, page_id=page_id)
    # Lo primero: qué permisos tiene EL TOKEN, no los que estén marcados en
    # el explorador. Teresa señaló —con razón— que los permisos ya estaban
    # puestos, y lo que se marca en la pantalla no es lo que lleva el token
    # que se generó hace días. Preguntárselo cuesta una llamada.
    try:
        perm = ig._req("GET", "me/permissions")
        dados = sorted(p["permission"] for p in perm.get("data", [])
                       if p.get("status") == "granted")
        otros = sorted(f"{p['permission']}({p.get('status')})"
                       for p in perm.get("data", []) if p.get("status") != "granted")
        print("PERMISOS DEL TOKEN:", ", ".join(dados) or "ninguno", flush=True)
        if otros:
            print("  no concedidos:", ", ".join(otros), flush=True)
        print("  ¿pages_read_engagement?",
              "SÍ" if "pages_read_engagement" in dados else "NO", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"No se pudieron leer los permisos: {type(e).__name__}: {e}", flush=True)
    print(flush=True)

    prueba = sys.argv[1:] or ["El Retiro Madrid", "Malasaña", "Mercado de San Fernando",
                              "Templo de Debod", "Misión Café Madrid"]
    print(f"Probando {len(prueba)} sitios\n", flush=True)
    bien = 0
    for nombre in prueba:
        ident, detalle = buscar(ig, nombre, usar_cache=False)
        print(f"{'ok  ' if ident else 'no  '} {nombre} → {ident or '—'} · {detalle}",
              flush=True)
        bien += 1 if ident else 0
    print(f"\n{bien} de {len(prueba)} encontrados", flush=True)
    if not bien:
        print("Ninguno: o el token no tiene permiso para buscar lugares, o la "
              "búsqueda de páginas ya no está disponible. Sin esto, se puede "
              "seguir publicando: simplemente sin ubicación.", flush=True)
