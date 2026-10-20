"""Dibuja las tarjetas de texto y los rótulos del canal, y las anima.

Por qué animadas: una tarjeta quieta cinco segundos es una diapositiva. Lo
que diferencia un vídeo de un pase de diapositivas no es la duración del
plano, es que en pantalla ocurra algo. Aquí ocurre poco y despacio a
propósito —el texto entra línea a línea, las cifras cuentan hacia arriba,
las filas de una comparación aparecen una detrás de otra— pero ocurre.

Lee tarjetas.yml y deja:

  graficos/T01.mp4      la tarjeta animada, que es lo que se monta
  graficos/T01.png      el fotograma final, para miniaturas y comprobaciones
  rotulos/R01.png       rótulo transparente, para poner encima de un clip

Mismos colores y mismas tipografías en todo, para que se vea como un mismo
canal.
"""
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

import config

BASE = Path(__file__).resolve().parent.parent
GRAFICOS = BASE / "graficos"
ROTULOS = BASE / "rotulos"

W, H = 1920, 1080
MARGEN = 180
FPS = 30
DURACION = 8.0          # más de lo que dura cualquier plano; luego se recorta
APARICION = 0.42        # lo que tarda en entrar cada capa
SUBIDA = 26             # píxeles que sube al entrar

FONDO = "#0E1014"
SUPERFICIE = "#20242C"
CLARO = "#F2F0EB"
APAGADO = "#9BA3B0"
AMBAR = "#D69E2E"

F = "/usr/share/fonts/truetype/dejavu/"
SANS = F + "DejaVuSans.ttf"
SANS_BOLD = F + "DejaVuSans-Bold.ttf"
MONO = F + "DejaVuSansMono.ttf"


def fuente(ruta, tam):
    return ImageFont.truetype(ruta, tam)


def ancho(d, texto, f):
    return d.textbbox((0, 0), texto, font=f)[2]


def cortar(d, texto, f, max_ancho):
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = f"{actual} {p}".strip()
        if ancho(d, prueba, f) <= max_ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def frenar(p):
    """Entra rápido y frena al final. Una rampa lineal se nota artificial."""
    return 1 - (1 - min(max(p, 0.0), 1.0)) ** 3


# ----------------------------------------------------------------- lienzo
class Lienzo:
    """Una tarjeta son capas que entran en momentos distintos.

    Una capa puede ser fija (se dibuja una vez) o viva (se vuelve a dibujar
    en cada fotograma, que es como cuenta una cifra hacia arriba).
    """

    def __init__(self):
        self.capas = []

    def capa(self, t=0.0):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.capas.append((im, t, None))
        return ImageDraw.Draw(im), im

    def viva(self, t, dur, pintar):
        self.capas.append((None, t, (dur, pintar)))


def _atenuar(im, a):
    if a >= 1:
        return im
    copia = im.copy()
    copia.putalpha(copia.getchannel("A").point(lambda v: int(v * a)))
    return copia


def componer(lienzo, t):
    base = Image.new("RGB", (W, H), FONDO)
    for im, t0, vivo in lienzo.capas:
        if t < t0:
            continue
        if vivo:
            dur, pintar = vivo
            capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            pintar(ImageDraw.Draw(capa), frenar((t - t0) / dur) if dur else 1.0)
        else:
            capa = im
        a = frenar((t - t0) / APARICION)
        dy = int((1 - a) * SUBIDA)
        base.paste(_atenuar(capa, a), (0, -dy), _atenuar(capa, a))
    return base


# --------------------------------------------------------------- piezas
def kicker(L, texto, t=0.0, y=170):
    if not texto:
        return
    d, _ = L.capa(t)
    d.text((MARGEN, y), texto.upper(), font=fuente(MONO, 30), fill=APAGADO)


def regla(L, y, t, largo=300, color=AMBAR, grosor=4):
    d, _ = L.capa(t)
    d.rectangle([MARGEN, y, MARGEN + largo, y + grosor], fill=color)


def encajar(d, texto, tam, maximo=None, negrita=True):
    maximo = maximo or (W - 2 * MARGEN)
    f = fuente(SANS_BOLD if negrita else SANS, tam)
    while ancho(d, texto, f) > maximo and f.size > 28:
        f = fuente(SANS_BOLD if negrita else SANS, f.size - 6)
    return f


# -------------------------------------------------------------- formatos
def capitulo(t):
    L = Lienzo()
    d0 = ImageDraw.Draw(Image.new("RGB", (W, H)))
    f_num, f_tit, f_sub = fuente(SANS_BOLD, 260), fuente(SANS, 76), fuente(MONO, 32)
    y = 330
    d, _ = L.capa(0.0)
    d.text((MARGEN, y), str(t["numero"]), font=f_num, fill="#2E3542")
    x = MARGEN + ancho(d0, str(t["numero"]), f_num) + 60
    d, _ = L.capa(0.30)
    d.text((x, y + 110), t["titulo"], font=f_tit, fill=CLARO)
    if t.get("nota"):
        d, _ = L.capa(0.60)
        d.text((x, y + 215), t["nota"].upper(), font=f_sub, fill=AMBAR)
    regla(L, y + 330, 0.85, 220)
    return L


def cifra(t):
    """La cifra cuenta hacia arriba. Es el momento en que el ojo se engancha."""
    L = Lienzo()
    kicker(L, t.get("etiqueta", ""))
    d0 = ImageDraw.Draw(Image.new("RGB", (W, H)))
    texto = str(t["numero"])
    f = encajar(d0, texto, t.get("tam", 300))
    color = AMBAR if t.get("acento") else CLARO

    m = re.search(r"\d[\d.,]*", texto)
    if m:
        crudo = m.group(0).replace(",", "")
        decimales = len(crudo.split(".")[1]) if "." in crudo else 0
        destino = float(crudo)
        antes, despues = texto[:m.start()], texto[m.end():]

        def pintar(d, p):
            v = destino * p
            cuenta = f"{v:,.{decimales}f}" if destino >= 1000 else f"{v:.{decimales}f}"
            d.text((MARGEN, 360), f"{antes}{cuenta}{despues}", font=f, fill=color)

        L.viva(0.25, 1.0, pintar)
    else:
        d, _ = L.capa(0.25)
        d.text((MARGEN, 360), texto, font=f, fill=color)

    if t.get("pie"):
        y = 360 + int(f.size * 1.2) + 30
        d, _ = L.capa(1.15)
        fp = fuente(SANS, 60)
        for ln in cortar(d, t["pie"], fp, W - 2 * MARGEN):
            d.text((MARGEN, y), ln, font=fp, fill=APAGADO)
            y += int(fp.size * 1.28)
    return L


def cita(t):
    L = Lienzo()
    kicker(L, t.get("etiqueta", ""))
    d0 = ImageDraw.Draw(Image.new("RGB", (W, H)))
    f = fuente(SANS, t.get("tam", 82))
    comillas = "“" + t["texto"] + "”"
    lineas = cortar(d0, comillas, f, W - 2 * MARGEN - 40)
    while len(lineas) > 5:
        f = fuente(SANS, f.size - 6)
        lineas = cortar(d0, comillas, f, W - 2 * MARGEN - 40)
    alto = len(lineas) * int(f.size * 1.3)
    y = (H - alto) // 2 - 40
    for i, ln in enumerate(lineas):
        d, _ = L.capa(0.25 + i * 0.16)
        d.text((MARGEN, y), ln, font=f, fill=CLARO)
        y += int(f.size * 1.3)
    if t.get("fuente"):
        regla(L, y + 60, 0.3 + len(lineas) * 0.16)
        d, _ = L.capa(0.45 + len(lineas) * 0.16)
        d.text((MARGEN, y + 110), t["fuente"], font=fuente(SANS, 46), fill=AMBAR)
    return L


def frase(t):
    L = Lienzo()
    kicker(L, t.get("etiqueta", ""))
    d0 = ImageDraw.Draw(Image.new("RGB", (W, H)))
    lineas = t["lineas"] if isinstance(t["lineas"], list) else [t["lineas"]]
    f = fuente(SANS_BOLD, t.get("tam", 92))
    def partir(fu):
        out = []
        for ln in lineas:
            out += cortar(d0, ln, fu, W - 2 * MARGEN) or [""]
        return out
    sueltas = partir(f)
    while len(sueltas) > 4:
        f = fuente(SANS_BOLD, f.size - 8)
        sueltas = partir(f)
    acento = t.get("acento", -1)
    alto = len(sueltas) * int(f.size * 1.25)
    y = (H - alto) // 2
    for i, ln in enumerate(sueltas):
        d, _ = L.capa(0.2 + i * 0.26)
        d.text((MARGEN, y), ln, font=f, fill=AMBAR if i == acento else CLARO)
        y += int(f.size * 1.25)
    return L


HUECO = 70          # aire mínimo entre la columna izquierda y la derecha


def caben(d0, izq, der):
    """Tamaños de letra con los que las dos columnas de una fila no se tocan.

    Una fila se dibuja con el texto de la izquierda pegado al margen y el de
    la derecha pegado al otro margen. Si entre los dos no cabe el ancho, se
    juntan sin ningún espacio y se lee «Except differencesunrelated to
    personal data», que fue exactamente lo que salió en pantalla durante
    trece segundos. Se baja el cuerpo de letra de esa fila hasta que entren.
    """
    hueco_util = W - 2 * MARGEN - HUECO
    for tam in range(64, 33, -4):
        f_k, f_v = fuente(SANS, tam), fuente(SANS_BOLD, tam)
        if ancho(d0, izq, f_k) + ancho(d0, der, f_v) <= hueco_util:
            return f_k, f_v
    return fuente(SANS, 34), fuente(SANS_BOLD, 34)


def lista(t):
    """Las filas caen una detrás de otra: se lee como una cuenta, no como un cuadro."""
    L = Lienzo()
    kicker(L, t.get("etiqueta", ""))
    d0 = ImageDraw.Draw(Image.new("RGB", (W, H)))
    filas = t["filas"]
    y = (H - len(filas) * 120) // 2
    for i, fila in enumerate(filas):
        izq, der = fila["de"], str(fila["a"])
        f_k, f_v = caben(d0, izq, der)
        t0 = 0.2 + i * 0.3
        d, _ = L.capa(t0)
        d.text((MARGEN, y), izq, font=f_k, fill=AMBAR if fila.get("acento") else APAGADO)
        d.text((W - MARGEN - ancho(d0, der, f_v), y), der, font=f_v,
               fill=AMBAR if fila.get("acento") else CLARO)
        y += 120
        if fila.get("raya"):
            d2, _ = L.capa(t0 + 0.12)
            d2.rectangle([MARGEN, y - 30, W - MARGEN, y - 28], fill=SUPERFICIE)
    if t.get("pie"):
        d, _ = L.capa(0.3 + len(filas) * 0.3)
        d.text((MARGEN, y + 60), t["pie"], font=fuente(SANS_BOLD, 64), fill=CLARO)
    return L


def rotulo(t):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f_t, f_s = fuente(SANS_BOLD, 56), fuente(MONO, 30)
    texto, sub = t["texto"], t.get("sub", "")
    an = max(ancho(d, texto, f_t), ancho(d, sub, f_s) if sub else 0)
    x, y = 150, H - 280
    alto = 150 if sub else 100
    d.rectangle([x - 40, y - 34, x + an + 60, y + alto], fill=(14, 16, 20, 243))
    d.rectangle([x - 40, y - 34, x - 32, y + alto], fill=AMBAR)
    d.text((x, y), texto, font=f_t, fill=CLARO)
    if sub:
        d.text((x, y + 80), sub.upper(), font=f_s, fill=AMBAR)
    return im




# =================================================== formatos que demuestran
#
# Los cinco de arriba enseñan texto. Están bien para una cita o un remate,
# pero si la pantalla solo repite la frase que se acaba de oír, el que lee
# rápido espera y el que escucha lee dos veces lo mismo. Estos cuatro enseñan
# algo que la voz no puede dar: una proporción, una comparación, un orden en
# el tiempo, un documento.


def rejilla(t):
    """Una cuadrícula donde una parte se apaga. Para enseñar una proporción.

    Mil pisos vacíos de cuarenta mil no es un número que nadie pueda imaginar.
    Cuarenta filas de mil ventanas tampoco se ven. Se dibuja una cuadrícula
    legible —cuarenta por veinticinco, mil celdas— y se apaga el porcentaje
    que toque, una a una. Lo que se entiende no es la cifra: es lo poco que
    es y lo mucho que vale.
    """
    L = Lienzo()
    kicker(L, t.get("etiqueta", ""))
    cols = int(t.get("columnas", 40))
    filas = int(t.get("filas_n", 25))
    total = cols * filas
    cuantas = max(1, round(total * float(t.get("porcentaje", 2.5)) / 100.0))
    ancho = (W - 2 * MARGEN) / cols
    lado = ancho * 0.62
    y0 = 300
    # El alto sale de lo que queda libre, no al revés: con veinticinco filas
    # a ojo la cuadrícula se salía por abajo y el pie no se veía.
    libre = H - y0 - (200 if t.get("pie") else 90)
    alto = max(6.0, libre / filas - 7)

    fondo, _ = L.capa(0.15)
    for i in range(total):
        cx = MARGEN + (i % cols) * ancho
        cy = y0 + (i // cols) * (alto + 7)
        fondo.rectangle([cx, cy, cx + lado, cy + alto], fill=SUPERFICIE)

    # Repartidas de verdad.
    #
    # Con un paso de total/cuantas, en una cuadrícula de cuarenta columnas y
    # mil celdas el paso era justo cuarenta: las veinticinco encendidas caían
    # todas en la primera columna, en una raya vertical. Un paso primo con el
    # número de columnas las esparce por toda la cuadrícula.
    paso = 613 if total % 613 else 617
    elegidas = sorted({(i * paso) % total for i in range(cuantas)})

    def pintar(d, p):
        cuantas_ya = int(len(elegidas) * p)
        for i in elegidas[:cuantas_ya]:
            cx = MARGEN + (i % cols) * ancho
            cy = y0 + (i // cols) * (alto + 7)
            d.rectangle([cx, cy, cx + lado, cy + alto], fill=AMBAR)
    L.viva(0.6, 2.4, pintar)

    if t.get("pie"):
        d, _ = L.capa(2.6)
        d.text((MARGEN, y0 + filas * (alto + 7) + 50), t["pie"],
               font=fuente(SANS_BOLD, 56), fill=CLARO)
    return L


def barras(t):
    """Barras que crecen. Para comparar cantidades que no se parecen en nada.

    Cero contra trescientos sesenta millones no se compara con dos cifras
    escritas: se compara viendo una barra que no existe al lado de una que no
    cabe.
    """
    L = Lienzo()
    kicker(L, t.get("etiqueta", ""))
    datos = t["barras"]
    tope = max(float(b["valor"]) for b in datos) or 1.0
    f_eti = fuente(SANS, 52)
    f_val = fuente(SANS_BOLD, 52)
    x0 = MARGEN + 520
    disponible = W - MARGEN - x0 - 320
    alto = 76
    hueco = 54
    y0 = (H - len(datos) * (alto + hueco)) // 2 + 40

    for i, b in enumerate(datos):
        y = y0 + i * (alto + hueco)
        d, _ = L.capa(0.2 + i * 0.25)
        d.text((MARGEN, y + 10), str(b["nombre"]), font=f_eti, fill=APAGADO)
        d.line([x0, y + alto + 10, W - MARGEN, y + alto + 10], fill=SUPERFICIE, width=2)

        largo = disponible * float(b["valor"]) / tope
        color = AMBAR if b.get("acento") else "#4A5261"

        def pintar(dd, p, y=y, largo=largo, color=color, b=b):
            ancho = max(3, largo * p)
            dd.rectangle([x0, y, x0 + ancho, y + alto], fill=color)
            # Una barra de cero mide tres píxeles, y el valor se metía encima
            # del nombre de la izquierda. Nunca más cerca de este margen.
            dd.text((max(x0 + ancho + 26, x0 + 120), y + 10), str(b.get("texto", "")),
                    font=f_val, fill=AMBAR if b.get("acento") else CLARO)
        L.viva(0.45 + i * 0.25, 1.1, pintar)

    if t.get("pie"):
        d, _ = L.capa(0.5 + len(datos) * 0.25)
        d.text((MARGEN, y0 + len(datos) * (alto + hueco) + 40), t["pie"],
               font=fuente(SANS_BOLD, 54), fill=CLARO)
    return L


def cronologia(t):
    """Una línea de tiempo que se traza. Para que el orden se vea, no se cuente.

    Lo que cuenta esta tarjeta no son las fechas sueltas sino la distancia
    entre ellas: quince meses hasta el acuerdo, diez más hasta el fallo.
    """
    L = Lienzo()
    kicker(L, t.get("etiqueta", ""))
    hitos = t["hitos"]
    x0, x1 = MARGEN + 40, W - MARGEN - 40
    y = H // 2 + 40
    f_fecha = fuente(MONO, 34)
    f_texto = fuente(SANS_BOLD, 46)

    def traza(d, p):
        d.line([x0, y, x0 + (x1 - x0) * p, y], fill=SUPERFICIE, width=5)
    L.viva(0.15, 1.6, traza)

    for i, h in enumerate(hitos):
        fx = x0 + (x1 - x0) * (i / max(len(hitos) - 1, 1))
        t0 = 0.5 + i * 0.45
        d, _ = L.capa(t0)
        acento = h.get("acento")
        col = AMBAR if acento else CLARO
        d.ellipse([fx - 13, y - 13, fx + 13, y + 13], fill=col)
        arriba = i % 2 == 0
        ty = y - 150 if arriba else y + 70
        ancho_txt = ancho(d, str(h["texto"]), f_texto)
        tx = min(max(fx - ancho_txt / 2, MARGEN), W - MARGEN - ancho_txt)
        d.text((tx, ty), str(h["texto"]), font=f_texto, fill=col)
        fecha = str(h.get("fecha", ""))
        if fecha:
            d.text((min(max(fx - ancho(d, fecha, f_fecha) / 2, MARGEN),
                        W - MARGEN - ancho(d, fecha, f_fecha)),
                    ty + (60 if arriba else -52)), fecha, font=f_fecha, fill=APAGADO)
    return L


def subrayado(t):
    """Un documento real con una línea trazándose bajo la frase que se lee.

    Es lo más parecido que tiene este canal a la mano que dibuja, y encaja
    donde aquella no encajaría: no decora, señala. La página sale de los PDF
    que ya descarga el paso de material.
    """
    L = Lienzo()
    pagina = Path(t["pagina"])
    if not pagina.is_absolute():
        pagina = BASE / pagina
    d0, _ = L.capa(0.0)
    if pagina.exists():
        doc = Image.open(pagina).convert("RGB")
        escala = min((W - 2 * MARGEN) / doc.width, (H - 240) / doc.height)
        doc = doc.resize((int(doc.width * escala), int(doc.height * escala)), Image.LANCZOS)
        ox, oy = (W - doc.width) // 2, (H - doc.height) // 2
        capa0 = L.capas[0][0]
        capa0.paste(doc, (ox, oy))
    else:
        ox = oy = 0
        d0.rectangle([MARGEN, 120, W - MARGEN, H - 120], fill="#F2F0EB")
        doc = Image.new("RGB", (W - 2 * MARGEN, H - 240))

    # La raya, en fracciones del ancho y el alto de la página.
    rx0 = ox + doc.width * float(t.get("x0", 0.08))
    rx1 = ox + doc.width * float(t.get("x1", 0.72))
    ry = oy + doc.height * float(t.get("y", 0.5))
    grosor = max(4, int(doc.height * 0.006))

    def pintar(d, p):
        d.line([rx0, ry, rx0 + (rx1 - rx0) * p, ry], fill=AMBAR, width=grosor)
    L.viva(0.8, 1.4, pintar)

    if t.get("pie"):
        d, _ = L.capa(2.2)
        f = fuente(SANS_BOLD, 50)
        texto = t["pie"]
        an = ancho(d, texto, f)
        d.rectangle([(W - an) // 2 - 30, H - 132, (W + an) // 2 + 30, H - 48], fill=FONDO)
        d.text(((W - an) // 2, H - 120), texto, font=f, fill=AMBAR)
    return L


FORMATOS = {"capitulo": capitulo, "cifra": cifra, "cita": cita,
            "frase": frase, "lista": lista, "rejilla": rejilla,
            "barras": barras, "cronologia": cronologia, "subrayado": subrayado}


# ------------------------------------------------------------------ main
def leible(t):
    """Cuánto hay que dejarla en pantalla para poder leerla.

    Una tarjeta que se va antes de que la hayas terminado de leer es peor
    que no ponerla: distrae y encima frustra. Se calcula por palabras, con
    un suelo generoso."""
    palabras = 0
    for clave in ("lineas", "texto", "pie", "titulo", "nota", "numero"):
        v = t.get(clave)
        if isinstance(v, list):
            palabras += sum(len(str(x).split()) for x in v)
        elif v:
            palabras += len(str(v).split())
    for fila in t.get("filas", []) or []:
        palabras += len(str(fila.get("de", "")).split()) + len(str(fila.get("a", "")).split())
    # Tres palabras se leen de un vistazo: «Side by side.» no necesita cuatro
    # segundos, y pedirlos obligaba a dejarla más tiempo del que la voz tarda
    # en decirlo, o a marcarla como ilegible cuando se leía de sobra.
    # La cuenta anterior —1,8 + 0,30 por palabra, con suelo de cuatro— pedía
    # casi siempre más tiempo del que la voz tarda en decir la frase. Una
    # tarjeta de seis palabras reclamaba cuatro segundos en un párrafo de tres,
    # así que o se salía o el montaje la tiraba. Se lee a unas tres palabras y
    # media por segundo; esto deja margen de sobra sin pedir imposibles.
    # Las pantallas que demuestran no se leen, se ven suceder: la rejilla
    # tarda tres segundos en encenderse, las barras en crecer, la línea en
    # trazarse. Pedirles el tiempo de sus cuatro palabras de pie las cortaba
    # a la mitad de la animación.
    # Cada una tarda lo suyo: la rejilla se enciende en tres segundos, las
    # barras crecen en algo más, la línea de tiempo pone un hito cada medio
    # segundo y el subrayado necesita que se lea lo subrayado.
    ANIMADAS = {"rejilla": 3.8, "barras": 4.6, "cronologia": 5.6, "subrayado": 5.2}
    if t.get("formato") in ANIMADAS:
        return ANIMADAS[t["formato"]]
    return round(min(9.5, max(2.2, 1.0 + 0.28 * palabras)), 2)


def escribir(lienzo, nombre):
    """Los fotogramas del movimiento y, después, el último congelado."""
    fin = max([t0 + (v[0] if v else APARICION) for _, t0, v in lienzo.capas] or [1.0])
    n = max(2, int((fin + 0.25) * FPS))
    tmp = Path(tempfile.mkdtemp())
    try:
        for i in range(n):
            componer(lienzo, i / FPS).save(tmp / f"f{i:04d}.png")
        ultimo = componer(lienzo, fin + 1)
        ultimo.save(GRAFICOS / f"{nombre}.png")
        resto = max(0.1, DURACION - n / FPS)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
             "-i", str(tmp / "f%04d.png"),
             "-vf", f"tpad=stop_mode=clone:stop_duration={resto:.2f},format=yuv420p",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
             str(GRAFICOS / f"{nombre}.mp4")], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    cfg = yaml.safe_load(config.ruta("tarjetas.yml").read_text(encoding="utf-8"))
    GRAFICOS.mkdir(exist_ok=True)
    ROTULOS.mkdir(exist_ok=True)

    n, duraciones = 0, {}
    for t in cfg.get("tarjetas", []):
        escribir(FORMATOS[t["formato"]](t), t["nombre"])
        duraciones[t["nombre"]] = leible(t)
        n += 1
        if n % 10 == 0:
            print(f"· {n} tarjetas animadas", flush=True)
    m = 0
    for t in cfg.get("rotulos", []):
        rotulo(t).save(ROTULOS / f"{t['nombre']}.png")
        m += 1
    import json
    (GRAFICOS / "duraciones.json").write_text(json.dumps(duraciones, indent=1),
                                              encoding="utf-8")
    print(f"· {n} tarjetas animadas y {m} rótulos dibujados", flush=True)
    print(f"· la más larga pide {max(duraciones.values()):.1f} s de lectura", flush=True)


if __name__ == "__main__":
    main()
