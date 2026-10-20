"""Dibuja las miniaturas del vídeo, en el mismo estilo que el canal.

Una miniatura se ve a 210 píxeles de ancho en el móvil. Ahí no cabe una
frase: caben tres o cuatro palabras enormes y nada más. Todo lo que no se
lea a ese tamaño sobra, por bonito que quede a tamaño completo.

  miniaturas/A-la-factura.png
  miniaturas/B-el-numero.png
  miniaturas/C-la-vuelta.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "miniaturas"

W, H = 1280, 720
MARGEN = 72

FONDO = "#0E1014"
CLARO = "#F2F0EB"
APAGADO = "#9BA3B0"
AMBAR = "#D69E2E"

F = "/usr/share/fonts/truetype/dejavu/"
SANS_BOLD = F + "DejaVuSans-Bold.ttf"
SANS = F + "DejaVuSans.ttf"
MONO = F + "DejaVuSansMono.ttf"


def f(ruta, tam):
    return ImageFont.truetype(ruta, tam)


def an(d, t, fu):
    return d.textbbox((0, 0), t, font=fu)[2]


def lienzo():
    im = Image.new("RGB", (W, H), FONDO)
    d = ImageDraw.Draw(im)
    # una banda ámbar a la izquierda: identifica el canal de un vistazo
    d.rectangle([0, 0, 14, H], fill=AMBAR)
    return im, d


def kicker(d, texto):
    d.text((MARGEN, 58), texto.upper(), font=f(MONO, 34), fill=APAGADO)


def pie(d, texto):
    fu = f(SANS_BOLD, 44)
    y = H - 118
    d.rectangle([MARGEN - 18, y - 16, MARGEN + an(d, texto, fu) + 24, y + 70],
                fill=AMBAR)
    d.text((MARGEN, y), texto, font=fu, fill="#15120A")


def encajar(d, texto, tam, maximo=None):
    """Baja el cuerpo hasta que la línea quepa de verdad."""
    maximo = maximo or (W - 2 * MARGEN - 20)
    fu = f(SANS_BOLD, tam)
    while an(d, texto, fu) > maximo and fu.size > 30:
        fu = f(SANS_BOLD, fu.size - 6)
    return fu


# ------------------------------------------------------------- miniaturas
def a_la_factura():
    """El contraste entre las dos cifras. Es la que más curiosidad genera."""
    im, d = lienzo()
    kicker(d, "hertz · atlanta")
    fu1 = encajar(d, "$80 DAMAGE", 150)
    fu2 = encajar(d, "$350 BILL", 150)
    d.text((MARGEN, 170), "$80 DAMAGE", font=fu1, fill=APAGADO)
    d.text((MARGEN, 330), "$350 BILL", font=fu2, fill=AMBAR)
    pie(d, "AND THAT WASN'T THE STORY")
    return im


def el_numero():
    """La caída en bolsa. Funciona si el espectador ya conoce la empresa."""
    im, d = lienzo()
    kicker(d, "hertz · one trading day")
    fu = f(SANS_BOLD, 250)
    d.text((MARGEN, 155), "−40%", font=fu, fill=AMBAR)
    x = MARGEN + an(d, "−40%", fu) + 56
    hueco = W - x - 40
    lineas = [("WHILE YOU", CLARO), ("WATCHED THE", CLARO), ("SCANNER", APAGADO)]
    fu2 = f(SANS_BOLD, 66)
    while max(an(d, t, fu2) for t, _ in lineas) > hueco and fu2.size > 34:
        fu2 = f(SANS_BOLD, fu2.size - 4)
    y = 215
    for t, color in lineas:
        d.text((x, y), t, font=fu2, fill=color)
        y += int(fu2.size * 1.32)
    pie(d, "THE PART NOBODY COVERED")
    return im


def la_vuelta():
    """La tesis, dicha en seco. La más honesta y la menos clickbait."""
    im, d = lienzo()
    kicker(d, "hertz · 2026")
    for i, (linea, color) in enumerate([("THE SCANNER", CLARO),
                                        ("WAS NEVER", CLARO),
                                        ("THE STORY", AMBAR)]):
        fu = encajar(d, linea, 120)
        d.text((MARGEN, 118 + i * 142), linea, font=fu, fill=color)
    pie(d, "IT WAS THE BALANCE SHEET")
    return im


# ---------------------------------------------- vídeo 2 · los precios
# La fórmula que funcionó en el vídeo 1 (16,7% de clics): dos cifras en
# tensión, enormes, y una frase corta en la banda ámbar. Se repite.
def v2_la_cesta():
    im, d = lienzo()
    kicker(d, "one grocery basket")
    fu1 = encajar(d, "SAME SHOP", 150)
    fu2 = encajar(d, "3 IN 4 PRICES", 150)
    d.text((MARGEN, 170), "SAME SHOP", font=fu1, fill=APAGADO)
    d.text((MARGEN, 330), "3 IN 4 PRICES", font=fu2, fill=AMBAR)
    pie(d, "WERE DIFFERENT")
    return im


def v2_la_negacion():
    im, d = lienzo()
    kicker(d, "delta, to congress")
    for i, (linea, color) in enumerate([("THEY SAY", APAGADO),
                                        ("THEY DON'T", CLARO),
                                        ("USE YOUR DATA", AMBAR)]):
        fu = encajar(d, linea, 120)
        d.text((MARGEN, 118 + i * 142), linea, font=fu, fill=color)
    pie(d, "THEY DON'T NEED TO")
    return im


# ------------------------------------------- vídeo 3 · las casas vacías
# Misma fórmula que en los dos anteriores: dos cifras en tensión, enormes, y
# una frase corta en la banda ámbar. Lo que cambia es cuál de las tres cifras
# del vídeo se pone delante, y no está claro cuál tira más: las mil casas son
# lo más concreto, el nueve de cada diez es lo más incómodo y la frase del
# juez es lo más nuevo.
def v3_mil_vacias():
    """Lo más concreto del vídeo, y lo que abre la narración."""
    im, d = lienzo()
    kicker(d, "one landlord · 40,000 flats")
    fu1 = encajar(d, "1,000 EMPTY", 150)
    fu2 = encajar(d, "ON PURPOSE", 150)
    d.text((MARGEN, 170), "1,000 EMPTY", font=fu1, fill=APAGADO)
    d.text((MARGEN, 330), "ON PURPOSE", font=fu2, fill=AMBAR)
    pie(d, "AND IT MADE MORE MONEY")
    return im


def v3_nueve_de_diez():
    """La cifra incómoda. Es la que sostiene el argumento entero."""
    im, d = lienzo()
    kicker(d, "the software sets the rent")
    fu = f(SANS_BOLD, 250)
    d.text((MARGEN, 155), "9/10", font=fu, fill=AMBAR)
    x = MARGEN + an(d, "9/10", fu) + 56
    hueco = W - x - 40
    lineas = [("LANDLORDS", CLARO), ("SAID YES.", CLARO), ("NOBODY SPOKE", APAGADO)]
    fu2 = f(SANS_BOLD, 66)
    while max(an(d, t, fu2) for t, _ in lineas) > hueco and fu2.size > 34:
        fu2 = f(SANS_BOLD, fu2.size - 4)
    y = 215
    for t, color in lineas:
        d.text((x, y), t, font=fu2, fill=color)
        y += int(fu2.size * 1.32)
    pie(d, "SO IT ISN'T A CARTEL")
    return im


def v3_es_expresion():
    """Lo más nuevo: la frase del 29 de septiembre, dicha en seco."""
    im, d = lienzo()
    kicker(d, "a federal judge · 29 september")
    for i, (linea, color) in enumerate([("A RENT PRICE", CLARO),
                                        ("IS NOW", CLARO),
                                        ("FREE SPEECH", AMBAR)]):
        fu = encajar(d, linea, 120)
        d.text((MARGEN, 118 + i * 142), linea, font=fu, fill=color)
    pie(d, "THAT'S THE RULING")
    return im


def main():
    SALIDA.mkdir(exist_ok=True)
    for nombre, hacer in (("V3-A-mil-vacias", v3_mil_vacias),
                          ("V3-B-nueve-de-diez", v3_nueve_de_diez),
                          ("V3-C-es-expresion", v3_es_expresion),
                          ("V2-A-la-cesta", v2_la_cesta),
                          ("V2-B-la-negacion", v2_la_negacion),
                          ("A-la-factura", a_la_factura),
                          ("B-el-numero", el_numero),
                          ("C-la-vuelta", la_vuelta)):
        hacer().save(SALIDA / f"{nombre}.png")
    print(f"· miniaturas en {SALIDA.name}/", flush=True)


if __name__ == "__main__":
    main()
