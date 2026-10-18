"""Qué se pone Allie, dónde está y en qué época del año vive.

POR QUÉ EXISTE. El 18 de octubre Teresa miró el perfil y dijo lo que yo no
había mirado: «siempre publicas a la misma chica con la misma prenda». Fui
al banco y tenía razón con creces — de 81 fotos:

    jersey de punto beige y variantes .... 17
    camisa de lino blanca ................  9
    gabardina beige ......................  9

La causa no era el generador de imágenes. Era que a quien escribe las
escenas NUNCA se le decía qué ropa poner, así que la elegía él; y un modelo
de lenguaje, cuando elige libremente, elige siempre lo mismo. Pedir
«variedad» no sirve: hay que imponer la prenda desde fuera.

Esto hace tres cosas:

  1. VESTUARIO. Una lista larga, con color y prenda concretos, y memoria de
     lo último usado para no repetir.
  2. SITIO. Madrid de verdad, no «una calle»: el Rastro un domingo no se
     parece a Malasaña un martes, y esa diferencia es la que hace que un
     perfil parezca una vida y no un catálogo.
  3. CALENDARIO. En qué estación estamos, qué tiempo hace en Madrid y qué
     hay en el horizonte — Todos los Santos, el cambio de hora, las luces de
     Navidad. Una foto con abrigo en julio canta; una castañera en noviembre
     la reconoce cualquiera que viva aquí.

Nada de esto toca la cara de Allie, que es sagrada y viene de la foto de
referencia.
"""
import json
import random
from datetime import date, datetime, timedelta

# --------------------------------------------------------------- vestuario
#
# Cada entrada: (nombre corto, descripción en inglés, estaciones).
# Estaciones: "i" invierno, "p" primavera, "v" verano, "o" otoño.
#
# La regla al escribirlas: COLOR CONCRETO. «A sweater» vuelve beige; «a
# forest-green ribbed turtleneck» vuelve verde. El beige está permitido,
# pero como una opción entre treinta y no como el mundo entero.
VESTUARIO = [
    ("burdeos-blazer", "an oversized burgundy wool blazer over a black top", "oi"),
    ("verde-cuello", "a forest-green ribbed turtleneck jumper", "io"),
    ("cuero-negro", "a black leather biker jacket over a white t-shirt", "op"),
    ("vaquero-claro", "a light-wash denim jacket over a striped navy breton top", "pv"),
    ("camel-abrigo", "a camel wool coat over a charcoal polo neck", "i"),
    ("mostaza-punto", "a mustard-yellow chunky knit jumper", "io"),
    ("rosa-palo", "a dusty-pink satin blouse", "pv"),
    ("cuadros", "a black-and-white checked wool overshirt", "io"),
    ("marino-trenca", "a navy duffle coat with a cream scarf", "i"),
    ("blanco-camisero", "a crisp white poplin shirt dress with a thin leather belt", "pv"),
    ("teja-cardigan", "a rust-orange oversized cardigan over a white vest top", "o"),
    ("gris-sudadera", "a heather-grey hoodie with the sleeves pushed up", "iop"),
    ("negro-punto", "a fitted black fine-knit jumper with a gold chain necklace", "iop"),
    ("verde-oliva", "an olive-green utility jacket over a cream t-shirt", "op"),
    ("lino-azul", "a pale-blue linen shirt worn loose", "pv"),
    ("vestido-flores", "a midi dress with a small dark floral print", "pv"),
    ("chaleco-punto", "a cream knitted vest over a pale-blue collared shirt", "op"),
    ("rojo-jersey", "a bright red crew-neck jumper", "io"),
    ("beige-gabardina", "a classic beige trench coat over a white shirt", "op"),
    ("plumifero", "a black quilted puffer jacket with a grey beanie", "i"),
    ("rayas-marinero", "a navy-and-white striped long-sleeve top", "pv"),
    ("chocolate-abrigo", "a chocolate-brown teddy coat", "i"),
    ("blusa-lunares", "a black blouse with small white polka dots", "iopv"),
    ("denim-mono", "a mid-blue denim boilersuit with the sleeves rolled", "pv"),
    ("malva-punto", "a lilac mohair jumper", "io"),
    ("negro-slip", "a black slip dress under a soft grey cardigan", "ov"),
    ("kaki-camisa", "a khaki oversized shirt worn open over a black tank top", "pv"),
    ("crudo-traje", "an off-white tailored blazer and matching trousers", "pv"),
    ("burdeos-punto", "a deep burgundy cable-knit jumper", "io"),
    ("tejano-camisa", "a washed denim shirt buttoned to the collar", "iopv"),
]

# ------------------------------------------------------------------ sitios
#
# Madrid concreto. «Una cafetería» sale siempre igual; «el mercado de San
# Fernando en Lavapiés» no.
SITIOS = [
    ("retiro", "walking under the plane trees in el Retiro park", "iopv"),
    ("malasana", "on a narrow street in Malasaña with old balconies behind her", "iopv"),
    ("debod", "at the Templo de Debod at sunset, city skyline behind", "iopv"),
    ("cava-baja", "on Cava Baja in La Latina, tiled bar fronts behind", "iopv"),
    ("azotea", "on a rooftop terrace over the Madrid skyline", "opv"),
    ("mercado", "inside Mercado de San Fernando in Lavapiés, stalls behind", "iopv"),
    ("cafe-ventana", "at a café window table with the street reflected in the glass", "iopv"),
    ("casa-sofa", "at home on a linen sofa with a wool throw", "io"),
    ("casa-cocina", "at home in a small bright kitchen with open shelves", "iopv"),
    ("letras", "in the Barrio de las Letras, bookshop window behind her", "iopv"),
    ("madrid-rio", "walking along Madrid Río with the bridges behind", "opv"),
    ("atocha", "in the tropical greenhouse of Atocha station", "iopv"),
    ("rosaleda", "in the rose garden of Parque del Oeste", "pv"),
    ("chamberi", "on a quiet Chamberí street with red-brick buildings", "iopv"),
    ("matadero", "in the brick courtyards of Matadero", "iopv"),
    ("gran-via", "crossing Gran Vía with lit signs behind her", "iopv"),
    ("libreria", "inside a small bookshop with full shelves behind", "iopv"),
    ("terraza-bar", "on a pavement terrace with woven chairs", "opv"),
    ("capricho", "in the wooded paths of El Capricho park", "op"),
    ("casa-ventana", "at home by a tall window with linen curtains", "iopv"),
]

# -------------------------------------------------------------- calendario
#
# Fechas que en Madrid significan algo. Sin esto, Allie vive en un octubre
# eterno. (mes, día, nombre, cuántos días antes empieza a tener sentido)
FECHAS = [
    (10, 31, "Halloween, que en Madrid se nota en escaparates y disfraces", 5),
    (11, 1, "el día de Todos los Santos: flores, cementerios y huesos de santo", 3),
    (11, 22, "el encendido de las luces de Navidad en Madrid", 4),
    (12, 22, "el sorteo de la lotería de Navidad", 3),
    (12, 24, "Nochebuena", 3),
    (12, 25, "Navidad", 1),
    (12, 31, "Nochevieja y las uvas en la Puerta del Sol", 3),
    (1, 5, "la cabalgata de Reyes", 2),
    (1, 6, "el día de Reyes", 1),
    (2, 14, "San Valentín", 3),
    (3, 8, "el 8 de marzo", 2),
    (4, 23, "el día del libro", 2),
    (5, 2, "el Dos de Mayo, fiesta de Madrid", 2),
    (5, 15, "San Isidro, las fiestas de Madrid", 4),
    (6, 24, "San Juan y el principio del verano", 2),
    (9, 1, "la vuelta a la rutina después del verano", 7),
    (10, 12, "el puente del Pilar", 3),
]

ESTACIONES = {
    (12, 1): ("invierno", "i", "frío seco de Madrid, cielo muy azul y sol bajo"),
    (3, 1): ("primavera", "p", "días templados, árboles florecidos y alguna lluvia"),
    (6, 1): ("verano", "v", "calor fuerte de Madrid, luz dura y sombra buscada"),
    (9, 1): ("otoño", "o", "tardes doradas, hojas en el suelo y fresco al anochecer"),
}


def estacion(hoy=None):
    """(nombre, letra, cómo se siente Madrid)."""
    hoy = hoy or date.today()
    m = hoy.month
    if m in (12, 1, 2):
        return ESTACIONES[(12, 1)]
    if m in (3, 4, 5):
        return ESTACIONES[(3, 1)]
    if m in (6, 7, 8):
        return ESTACIONES[(6, 1)]
    return ESTACIONES[(9, 1)]


def cambio_de_hora(hoy):
    """El último domingo de octubre y el último de marzo, que en Madrid se
    comentan solos: de pronto anochece a las seis."""
    for mes, texto in ((10, "esta noche se cambia la hora y anochecerá antes"),
                       (3, "esta noche se cambia la hora y habrá más tarde")):
        if hoy.month != mes:
            continue
        d = date(hoy.year, mes, 31)
        while d.weekday() != 6:
            d -= timedelta(days=1)
        if 0 <= (d - hoy).days <= 3:
            return texto
    return None


def fechas_cerca(hoy=None):
    """Lo que viene en los próximos días y merece una mención."""
    hoy = hoy or date.today()
    cerca = []
    for mes, dia, nombre, antelacion in FECHAS:
        for ano in (hoy.year, hoy.year + 1):
            try:
                d = date(ano, mes, dia)
            except ValueError:
                continue
            faltan = (d - hoy).days
            if 0 <= faltan <= antelacion:
                cerca.append((faltan, nombre))
    extra = cambio_de_hora(hoy)
    if extra:
        cerca.append((0, extra))
    cerca.sort()
    return [n for _, n in cerca]


def momento(hoy=None):
    """El párrafo de contexto que se le da a quien escribe las escenas."""
    hoy = hoy or date.today()
    nombre, letra, tiempo = estacion(hoy)
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    partes = [f"Hoy es {dias[hoy.weekday()]} {hoy.day} de "
              f"{['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'][hoy.month - 1]}.",
              f"En Madrid es {nombre}: {tiempo}."]
    cerca = fechas_cerca(hoy)
    if cerca:
        partes.append("Está cerca " + "; ".join(cerca) + ".")
    return " ".join(partes), letra


# ----------------------------------------------------------------- elegir
def _de_temporada(lista, letra):
    buenas = [x for x in lista if letra in x[2]]
    return buenas or list(lista)


def elegir(letra, usados_vestuario=(), usados_sitio=(), semilla=None):
    """(vestuario, sitio) de la temporada, evitando lo usado últimamente.

    Evitar lo reciente es la mitad del trabajo: con treinta prendas y
    elección al azar, la misma sale dos veces por semana y parece que no
    hemos cambiado nada.
    """
    az = random.Random(semilla)
    v = _de_temporada(VESTUARIO, letra)
    s = _de_temporada(SITIOS, letra)
    libres_v = [x for x in v if x[0] not in usados_vestuario] or v
    libres_s = [x for x in s if x[0] not in usados_sitio] or s
    return az.choice(libres_v), az.choice(libres_s)


def ultimos(indice, cuantos=8):
    """Lo usado en las últimas tandas, leído del índice del banco."""
    fotos = indice.get("fotos", []) if isinstance(indice, dict) else []
    vest, sitio = [], []
    for f in sorted(fotos, key=lambda x: str(x.get("creada", "")), reverse=True):
        if f.get("vestuario") and f["vestuario"] not in vest:
            vest.append(f["vestuario"])
        if f.get("sitio") and f["sitio"] not in sitio:
            sitio.append(f["sitio"])
        if len(vest) >= cuantos and len(sitio) >= cuantos:
            break
    return vest[:cuantos], sitio[:cuantos]


if __name__ == "__main__":
    texto, letra = momento()
    print(texto)
    print(f"temporada: {letra}")
    for _ in range(5):
        v, s = elegir(letra)
        print(f"  · {v[1]} — {s[1]}")
    print(json.dumps({"fechas_cerca": fechas_cerca()}, ensure_ascii=False))
