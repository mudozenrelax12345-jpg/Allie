"""Fotos reales de cada sitio, con licencia libre, desde Wikimedia Commons.

DE DÓNDE SALE ESTO. El 23 de octubre el primer vídeo del formato «dato»
hablaba del templo de Debod, de Botín, de la Casa de Campo, del metro de
Chamberí y de la Gran Vía… enseñando siempre la misma calle de tapas con
Allie delante. Veinticuatro segundos de una imagen que no cuenta nada de lo
que se está diciendo. Teresa lo dijo en una línea: «es una mierda». Lo era.

Un vídeo de «¿sabías que…?» tiene que ENSEÑAR la cosa. Y las fotos de los
sitios no se pueden inventar con IA: un templo de Debod inventado es un
templo que no existe, y el dato deja de ser un dato.

LA LICENCIA ES LO QUE DECIDE, no la calidad. Esto solo se queda con dominio
público, CC0 y CC BY. Deliberadamente NO coge CC BY-SA: esa licencia obliga
a publicar la obra derivada —el vídeo entero— con la misma licencia, y eso
es una decisión que no me toca tomar por una cuenta ajena. Si un sitio no
tiene ninguna foto libre, se dice y se deja sin foto, que es mejor que
colarla.

LA ATRIBUCIÓN SE GUARDA SIEMPRE, incluso para dominio público, donde no hace
falta. Queda en estado/creditos-fotos.json para que el pie de la publicación
pueda llevar los créditos. CC BY sin crédito es una infracción, no un
descuido.

ESTO NO CORRE EN MI MÁQUINA. El entorno donde escribo no llega a Wikimedia:
la salida a internet está limitada a los repositorios de paquetes y a
GitHub. La máquina que monta los vídeos sí llega, así que esto se ejecuta
allí. Por eso no depende de ninguna biblioteca que haya que instalar.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DESTINO = BASE / "video" / "lugares"
CREDITOS = BASE / "estado" / "creditos-fotos.json"

API = "https://commons.wikimedia.org/w/api.php"
AGENTE = "AllieBot/1.0 (https://github.com/mudozenrelax12345-jpg/Allie)"

# Las etiquetas de licencia tal y como las devuelve Commons. La lista es
# blanca a propósito: lo que no esté aquí, no entra.
LIBRES = {
    "cc0", "cc zero", "public domain", "pd", "pd-old", "pd-self", "pd-us",
    "cc by 1.0", "cc by 2.0", "cc by 2.5", "cc by 3.0", "cc by 4.0",
    "attribution",
}
ANCHO = 1400


def log(m):
    print(f"· {m}", flush=True)


def limpiar(html):
    """Commons devuelve el autor como un trozo de HTML."""
    import re
    t = re.sub(r"<[^>]+>", " ", html or "")
    t = t.replace("&amp;", "&").replace("&nbsp;", " ").replace("&quot;", '"')
    return " ".join(t.split())[:120]


def pedir(params, intentos=3):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            ultimo = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"Commons no responde: {ultimo}")


def es_libre(meta):
    etq = (meta.get("LicenseShortName", {}).get("value") or "").strip().lower()
    if etq in LIBRES:
        return etq
    # Algunas fichas solo traen el campo «License» en forma de código.
    cod = (meta.get("License", {}).get("value") or "").strip().lower()
    if cod in ("cc0", "pd", "cc-by-4.0", "cc-by-3.0", "cc-by-2.0"):
        return cod
    return None


COMMONS_SELLOS = (
    ("featured pictures", 400),
    ("quality images", 250),
    ("valued images", 120),
)


def nota(cand, termino):
    """Cuánto vale una candidata. No es la resolución.

    Ordenando por tamaño salía, para «Templo de Debod», una foto nevada con
    un músico callejero delante en la que el templo parecía un bloque de
    piedra cualquiera. Era la más grande del montón y la peor de todas: una
    foto que no deja reconocer la cosa de la que habla el dato no sirve, por
    muchos megapíxeles que tenga.

    Quien ya ha hecho este trabajo es la propia Commons. Sus comunidades
    marcan las fotos buenas con tres sellos —«featured», «quality» y
    «valued»— y esa valoración vale muchísimo más que cualquier regla que
    yo pueda escribir mirando metadatos. Eso manda; el tamaño solo desempata.
    """
    puntos = 0
    cats = " ".join(cand.get("categorias") or []).lower()
    for sello, valor in COMMONS_SELLOS:
        if sello in cats:
            puntos += valor
            break
    # Que el título hable del sitio, no de un detalle suyo.
    titulo = cand["titulo"].lower()
    claves = [p for p in termino.lower().split() if len(p) > 3]
    puntos += 25 * sum(1 for k in claves if k in titulo)
    puntos += min(cand["ancho"] * cand["alto"] / 1_000_000, 20)
    return puntos


# Palabras que no distinguen nada: salen en media Commons.
GENERICAS = {"madrid", "españa", "spain", "vista", "aerea", "aérea", "foto",
             "panoramica", "panorámica", "street", "city", "calle", "atardecer",
             "noche", "skyline", "temple", "museo", "estacion", "estación"}


def habla_del_sitio(cand, termino):
    """Que la foto sea DE ESO, y no de otra cosa que está en Madrid.

    Buscando «Casa de Campo Madrid vista aérea» salió elegida «Madrid.
    Estación del Norte, septiembre de 1979», que no tiene nada que ver: el
    buscador se quedó con «Madrid» y la nota la premió por eso. Puntuar el
    parecido no basta, porque una foto sin ningún parecido también puntúa
    si las demás puntúan poco.

    Así que esto no es una puntuación, es un requisito: al menos una
    palabra que distinga de verdad —quitando las que salen en media
    Commons— tiene que aparecer en el título o en las categorías.
    """
    claves = [p for p in termino.lower().replace(",", " ").split()
              if len(p) > 3 and p not in GENERICAS]
    if not claves:
        return True
    donde = (cand["titulo"] + " " + " ".join(cand.get("categorias") or [])).lower()
    return any(k in donde for k in claves)


def _ordenar(salida, termino):
    fuera = len(salida)
    salida = [c for c in salida if habla_del_sitio(c, termino)]
    if fuera - len(salida):
        log(f"    descartadas {fuera - len(salida)} que no hablan del sitio")
    salida.sort(key=lambda x: -nota(x, termino))
    for c in salida[:5]:
        log(f"    candidata {nota(c, termino):6.0f} · {c['titulo'][5:58]} · "
            f"{c['licencia']}")
    return salida


def _cosechar(d, termino, exacto=False):
    """Las páginas que devuelve Commons, filtradas por formato y licencia."""
    salida = []
    for pag in (d.get("query", {}).get("pages") or {}).values():
        inf = (pag.get("imageinfo") or [{}])[0]
        if not inf.get("thumburl"):
            continue
        if inf.get("mime") not in ("image/jpeg", "image/png"):
            continue
        # Horizontal o cuadrada. Una foto muy apaisada o muy estrecha no
        # llena el hueco de la foto sin recortar lo que importa.
        an, al = inf.get("width") or 0, inf.get("height") or 0
        if not exacto and not (0.7 <= (an / al if al else 0) <= 2.6):
            continue
        if not exacto and an < 800:
            continue
        lic = es_libre(inf.get("extmetadata") or {})
        if not lic:
            continue
        meta = inf.get("extmetadata") or {}
        salida.append({
            "categorias": [c.get("title", "") for c in (pag.get("categories") or [])],
            "titulo": pag.get("title", ""),
            "url": inf["thumburl"],
            "pagina": inf.get("descriptionurl", ""),
            "licencia": lic,
            "autor": limpiar(meta.get("Artist", {}).get("value")),
            "ancho": an, "alto": al,
        })
    return salida


def buscar(termino, cuantas=30):
    """Las candidatas de Commons para un término, ya filtradas por licencia.

    Un término que empieza por «File:» no se busca: se pide ese fichero y
    punto. Es la salida de emergencia para cuando el buscador no acierta y
    yo ya he visto cuál es la buena. Sigue pasando el filtro de licencia:
    elegirla a mano no la hace libre.
    """
    if termino.startswith(("File:", "Archivo:")):
        d = pedir({"action": "query", "titles": termino,
                   "prop": "imageinfo|categories",
                   "iiprop": "url|size|extmetadata|mime",
                   "iiurlwidth": str(ANCHO), "cllimit": "max"})
        return _ordenar(_cosechar(d, termino, exacto=True), termino)
    d = pedir({
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{termino} filetype:bitmap",
        "gsrnamespace": "6",          # 6 = ficheros
        "gsrlimit": str(cuantas),
        "prop": "imageinfo|categories",
        "iiprop": "url|size|extmetadata|mime",
        "iiurlwidth": str(ANCHO),
        "cllimit": "max",
    })
    return _ordenar(_cosechar(d, termino), termino)





def bajar(url, destino):
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=60) as r:
        datos = r.read()
    if len(datos) < 20000:
        raise RuntimeError(f"la foto pesa {len(datos)} bytes: no me fío")
    destino.write_bytes(datos)
    return len(datos)


def conseguir(terminos):
    """Una foto libre por término. Devuelve (rutas, créditos).

    Si un término no da ninguna foto libre, su hueco va a None y quien
    llame decide: aquí no se rellena con cualquier cosa.
    """
    DESTINO.mkdir(parents=True, exist_ok=True)
    CREDITOS.parent.mkdir(parents=True, exist_ok=True)
    rutas, creditos = [], []
    for i, entrada in enumerate(terminos):
        # Cada sitio puede traer varios términos: el primero que dé una foto
        # libre, gana. Hace falta porque el buscador de Commons es literal y
        # porque en algunos sitios casi todo es CC BY-SA, que aquí no entra:
        # a Debod y a Chamberí no les encontró nada con un solo término.
        alternativos = [entrada] if isinstance(entrada, str) else list(entrada)
        t = alternativos[0]
        cand = []
        for alt in alternativos:
            try:
                cand = buscar(alt)
            except Exception as e:  # noqa: BLE001
                log(f"«{alt}»: Commons falló ({e})")
                continue
            if cand:
                t = alt
                break
            log(f"«{alt}»: nada libre, pruebo otro término")
        if not cand:
            log(f"«{alternativos[0]}»: ninguna foto con licencia libre")
            rutas.append(None)
            continue
        puesto = None
        for c in cand[:4]:
            ruta = DESTINO / f"{i:02d}.jpg"
            try:
                peso = bajar(c["url"], ruta)
            except Exception as e:  # noqa: BLE001
                log(f"«{t}»: no baja {c['titulo']} ({e})")
                continue
            puesto = c
            log(f"«{t}» · {c['titulo'][5:60]} · {c['licencia']} · "
                f"{c['ancho']}×{c['alto']} · {peso/1000:.0f} kB")
            break
        if not puesto:
            rutas.append(None)
            continue
        rutas.append(DESTINO / f"{i:02d}.jpg")
        creditos.append({"termino": t, **{k: puesto[k] for k in
                                          ("titulo", "licencia", "autor", "pagina")}})
    CREDITOS.write_text(json.dumps(creditos, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    return rutas, creditos


def pie_creditos(creditos):
    """La línea de créditos para el pie de la publicación.

    El dominio público no la necesita; CC BY sí, y no ponerla es incumplir
    la licencia. Como el pie de un reel es corto, se abrevia al autor y la
    licencia, que es lo que la licencia exige nombrar.
    """
    partes = []
    for c in creditos:
        if c["licencia"] in ("cc0", "cc zero", "public domain", "pd",
                             "pd-old", "pd-self", "pd-us"):
            continue
        autor = c["autor"] or "Wikimedia Commons"
        partes.append(f"{autor} ({c['licencia'].upper()})")
    if not partes:
        return ""
    return "Fotos: " + " · ".join(dict.fromkeys(partes)) + " · vía Wikimedia Commons"


if __name__ == "__main__":
    terminos = sys.argv[1:] or [os.environ.get("TERMINO", "Templo de Debod")]
    rutas, cred = conseguir(terminos)
    print()
    for t, r in zip(terminos, rutas):
        print(f"  {'OK ' if r else 'NO '} {t}")
    print()
    print(pie_creditos(cred) or "(sin créditos obligatorios)")
