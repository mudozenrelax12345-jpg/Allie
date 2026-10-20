"""Compone el lecho musical del vídeo. Original, así que no hay licencia.

La música de archivo gratuita siempre tiene letra pequeña: atribución
obligatoria, o reclamaciones automáticas de derechos en YouTube. Componerla
desde cero quita el problema de raíz — no hay nada que acreditar ni nada que
nadie pueda reclamar, porque no existe en ningún catálogo.

No es una canción: es un lecho. Tiene que sostener la voz sin que te des
cuenta de que está. Por eso es lento, grave, sin melodía que siga el oído y
sin percusión marcada.

  musica/lecho.wav

La armonía cambia con los actos: el acto de la máquina es mecánico, el del
24 de junio aprieta, el del cierre se abre un poco.
"""
import json
import math
import os
import wave
from pathlib import Path

import numpy as np

import config

BASE = Path(__file__).resolve().parent.parent
AUDIO = BASE / "audio"
SALIDA = BASE / "musica" / "lecho.wav"

SR = 44100

# Cada vídeo tiene su color. Dos vídeos seguidos con la misma música de
# fondo suenan a plantilla, por mucho que el resto esté bien. Se configura
# en la sección «musica:» del montaje de cada vídeo.
PULSO = 62                      # pulsaciones por minuto
COMPAS = 60.0 / PULSO * 4


def nota(n):
    """Frecuencia de una nota MIDI. 62 = re3."""
    return 440.0 * 2 ** ((n - 69) / 12)


ACORDES = {
    # modo sobrio: séptimas y novenas, que suenan abiertas y sin juicio
    "Fmaj9":  [53, 60, 64, 67, 72],
    "Am7":    [57, 64, 67, 71, 76],
    "Csus2":  [48, 55, 62, 67, 71],
    "Bbmaj7": [46, 53, 57, 62, 65],
    "Gm7":    [55, 62, 65, 69, 74],
    "Dm7":    [50, 57, 60, 65, 72],
    # modo tenso: tríadas cerradas en menor
    "Dm":  [50, 57, 62, 65, 69],
    "Bb":  [46, 53, 58, 62, 65],
    "Gm":  [43, 50, 55, 58, 62],
    "F":   [41, 48, 53, 57, 60],
    "Am":  [45, 52, 57, 60, 64],
    "C":   [48, 55, 60, 64, 67],
    "A":   [45, 52, 57, 61, 64],
}

# El guion dice expresamente que la máquina NO es el villano. Si la música
# dice lo contrario, el espectador le cree a la música. Por eso el modo
# sobrio es el que va: curioso y algo melancólico, nunca amenazante.
SOBRIO = {
    1: {"acordes": ["Fmaj9", "Am7"],                        "pulso": 0.0,  "grave": 0},
    2: {"acordes": ["Csus2", "Fmaj9", "Am7", "Bbmaj7"],     "pulso": 0.0,  "grave": 0},
    3: {"acordes": ["Am7", "Gm7", "Fmaj9", "Csus2"],        "pulso": 0.0,  "grave": 0},
    4: {"acordes": ["Fmaj9", "Dm7", "Bbmaj7", "Csus2"],     "pulso": 0.0,  "grave": -12},
    5: {"acordes": ["Dm7", "Gm7", "Csus2", "Fmaj9"],        "pulso": 0.28, "grave": -12},
    6: {"acordes": ["Bbmaj7", "Fmaj9", "Csus2", "Am7"],     "pulso": 0.0,  "grave": 0},
}

TENSO = {
    1: {"acordes": ["Dm", "Bb"],              "pulso": 0.0,  "grave": -12},
    2: {"acordes": ["Dm", "Gm", "Dm", "Bb"],  "pulso": 0.55, "grave": -12},
    3: {"acordes": ["Bb", "F", "Gm", "Dm"],   "pulso": 0.35, "grave": -12},
    4: {"acordes": ["Dm", "Am", "Dm", "Gm"],  "pulso": 0.25, "grave": -12},
    5: {"acordes": ["Gm", "Dm", "A", "Dm"],   "pulso": 0.85, "grave": -12},
    6: {"acordes": ["F", "C", "Gm", "Dm"],    "pulso": 0.2,  "grave": -12},
}

TONO = os.environ.get("TONO_MUSICA", "sobrio").strip().lower()
PLAN = TENSO if TONO == "tenso" else SOBRIO

# Paletas. La familia es la misma —acordes abiertos, nada de amenaza— pero
# cada vídeo tiene su tonalidad, su tempo y su textura.
PALETAS = {
    "hertz": {       # vídeo 1: fa mayor, lento, solo acordes sostenidos
        "pulso": 62, "transporte": 0, "ostinato": 0.0,
    },
    "precios": {     # vídeo 2: tres semitonos abajo, algo más rápido, y un
                     # pulso repetido muy suave: el sonido de algo que calcula
        "pulso": 72, "transporte": -3, "ostinato": 0.34,
    },
    "vacio": {       # vídeo 3: otra pieza entera. Cuartas y madera, lenta y
                     # con hueco. Ver componer_vacio() más abajo.
        "pulso": 54, "transporte": 0, "ostinato": 0.0, "motor": "vacio",
    },
}


def paleta():
    import yaml
    try:
        m = yaml.safe_load(config.ruta("montaje.yml").read_text(encoding="utf-8"))
        nombre = (m.get("musica") or {}).get("paleta", "")
    except Exception:  # noqa: BLE001
        nombre = ""
    return PALETAS.get(nombre, PALETAS["hertz"])


def sobre(n, subida, bajada):
    """Entrada y salida suaves. Sin esto se oyen chasquidos en cada nota."""
    e = np.ones(n)
    s = min(int(subida * SR), n // 2)
    b = min(int(bajada * SR), n - s)
    if s:
        e[:s] = np.linspace(0, 1, s) ** 2
    if b:
        e[n - b:] = np.linspace(1, 0, b) ** 2
    return e


def cuerda(freq, dur, armonicos=5, desafine=0.12):
    """Un timbre cálido: la fundamental y unos pocos armónicos que decaen.

    El ligero desafine entre las dos mitades del estéreo es lo que hace que
    suene ancho en vez de plano.
    """
    t = np.linspace(0, dur, int(dur * SR), endpoint=False)
    izq = np.zeros_like(t)
    der = np.zeros_like(t)
    for k in range(1, armonicos + 1):
        peso = 1.0 / (k ** 1.7)
        # un vibrato lentísimo, por debajo del umbral de atención
        lfo = 1 + 0.0015 * np.sin(2 * np.pi * (0.07 + 0.013 * k) * t)
        izq += peso * np.sin(2 * np.pi * freq * k * lfo * t + k)
        der += peso * np.sin(2 * np.pi * (freq + desafine) * k * lfo * t + k * 1.7)
    return np.stack([izq, der], axis=1)


def grave(freq, dur):
    """El zumbido de fondo. Casi todo fundamental, sin brillo."""
    t = np.linspace(0, dur, int(dur * SR), endpoint=False)
    resp = 1 + 0.03 * np.sin(2 * np.pi * 0.05 * t)       # respira muy despacio
    onda = (np.sin(2 * np.pi * freq * t * resp)
            + 0.22 * np.sin(2 * np.pi * freq * 2 * t)
            + 0.05 * np.sin(2 * np.pi * freq * 3 * t))
    return np.stack([onda, onda], axis=1)


def pizca(freq, dur=0.9):
    """Una nota corta y clara, como una gota. Para el pulso repetido."""
    t = np.linspace(0, dur, int(dur * SR), endpoint=False)
    caida = np.exp(-t * 5.5)
    onda = (np.sin(2 * np.pi * freq * t)
            + 0.30 * np.sin(2 * np.pi * freq * 2 * t)
            + 0.12 * np.sin(2 * np.pi * freq * 3.01 * t)) * caida
    return np.stack([onda, onda * 0.92], axis=1)


def golpe(dur=1.4):
    """Un pulso sordo, como un latido. Marca el tiempo sin ser percusión."""
    t = np.linspace(0, dur, int(dur * SR), endpoint=False)
    caida = np.exp(-t * 7)
    tono = np.sin(2 * np.pi * (58 * np.exp(-t * 9) + 41) * t) * caida
    cuerpo = tono * 0.8
    return np.stack([cuerpo, cuerpo], axis=1)


def aire(dur, color=0.7):
    """Un siseo muy suave, para que el silencio no suene a vacío digital."""
    n = int(dur * SR)
    ruido = np.random.default_rng(7).normal(0, 1, (n, 2))
    # filtro paso bajo de un polo, aplicado dos veces: queda un soplo mate
    a = 0.0008 + 0.0012 * color
    for _ in range(2):
        salida = np.zeros_like(ruido)
        acc = np.zeros(2)
        for i in range(0, n, 4096):                     # por bloques, por memoria
            trozo = ruido[i:i + 4096]
            for j in range(len(trozo)):
                acc = acc + a * (trozo[j] - acc)
                salida[i + j] = acc
        ruido = salida
    return ruido / (np.max(np.abs(ruido)) + 1e-9)


# ===================================================================== vacío
#
# El vídeo 3 no puede sonar como los dos anteriores, y los dos anteriores
# suenan igual: comparten los mismos acordes y los mismos instrumentos, y solo
# cambian de tempo y de tonalidad. Esto es otra pieza, no otra versión.
#
# Qué cambia de verdad:
#
#   · La armonía deja de apilarse por terceras y se apila por CUARTAS. Un
#     acorde de cuartas no es alegre ni triste: no tiene el grado que decide
#     eso. Suena abierto, frío y sin resolver. Para un vídeo sobre mil pisos
#     vacíos, es el color exacto.
#
#   · Delante ya no hay una cuerda sostenida sino una MADERA que golpea y
#     calla. El sonido no llena: deja hueco entre nota y nota.
#
#   · La figura de madera va de tres contra el compás de cuatro, así que
#     nunca cae donde esperas y tarda cuatro compases en volver a cuadrar.
#     Es movimiento sin amenaza. Y suena a alguien contando.

CUARTAS = {
    "Q-la":  [45, 50, 55, 60, 65],
    "Q-re":  [50, 55, 60, 65, 70],
    "Q-sol": [43, 48, 53, 58, 63],
    "Q-mi":  [40, 45, 50, 55, 60],
    "Q-do":  [48, 53, 58, 63, 68],
    "Q-fa":  [41, 46, 51, 56, 61],
}

# Un acto, un color. Y la figura de madera va creciendo: empieza con dos
# notas y acaba con cuatro, para que el final tenga más que el principio sin
# subir el volumen ni meter tambores.
VACIO = {
    1: {"acordes": ["Q-la", "Q-mi"],                   "notas": 2, "octava": 0},
    2: {"acordes": ["Q-re", "Q-la", "Q-sol"],          "notas": 3, "octava": 0},
    3: {"acordes": ["Q-sol", "Q-re", "Q-do"],          "notas": 3, "octava": 12},
    4: {"acordes": ["Q-mi", "Q-la", "Q-re"],           "notas": 3, "octava": 0},
    5: {"acordes": ["Q-do", "Q-sol", "Q-re", "Q-la"],  "notas": 4, "octava": 12},
    6: {"acordes": ["Q-fa", "Q-do", "Q-sol", "Q-la"],  "notas": 2, "octava": 0},
}


def madera(freq, dur=2.2):
    """Un mazo sobre madera: ataque corto, cola que se apaga enseguida.

    Lo que lo hace de madera y no de metal es que los armónicos no están en
    múltiplos exactos de la fundamental, y que los agudos se apagan mucho
    antes que el grave. Un metal mantiene el brillo; la madera lo pierde en
    la primera décima de segundo.
    """
    t = np.linspace(0, dur, int(dur * SR), endpoint=False)
    onda = np.zeros_like(t)
    for mult, peso, caida in ((1.0, 1.00, 2.6), (3.94, 0.52, 6.5),
                              (9.2, 0.22, 11.0), (2.01, 0.26, 4.2)):
        onda += peso * np.sin(2 * np.pi * freq * mult * t) * np.exp(-t * caida)
    # el golpe del mazo: un chasquido muy corto de ruido
    golpecito = np.random.default_rng(int(freq) % 997).normal(0, 1, len(t))
    onda += 0.11 * golpecito * np.exp(-t * 120)
    onda *= sobre(len(onda), 0.004, dur * 0.5)
    return np.stack([onda, onda * 0.93], axis=1)


def componer_vacio(pista, actos, total, pal):
    """La pieza del vídeo 3. Madera delante, cuartas detrás, y hueco."""
    compas = 60.0 / pal["pulso"] * 4
    tr = pal["transporte"]
    for idx, (acto, inicio) in enumerate(actos):
        fin = actos[idx + 1][1] if idx + 1 < len(actos) else total
        plan = VACIO.get(acto, VACIO[1])
        sec = plan["acordes"]

        # --- el fondo de cuartas, muy atrás -----------------------------
        t, paso = inicio, 0
        while t < fin:
            acorde = [x + tr for x in CUARTAS[sec[paso % len(sec)]]]
            dur = min(compas * 2, fin - t) + 3.0
            for grado, midi in enumerate(acorde[1:4]):
                voz = cuerda(nota(midi), dur, armonicos=3, desafine=0.09)
                voz *= sobre(len(voz), 2.8, 3.2)[:, None]
                mezclar(pista, voz, t, 0.030 / (1 + grado * 0.5))
            raiz = grave(nota(acorde[0] - 12), dur)
            raiz *= sobre(len(raiz), 3.0, 3.0)[:, None]
            mezclar(pista, raiz, t, 0.065)
            t += compas * 2
            paso += 1

        # --- la madera, delante -----------------------------------------
        # Tres golpes por cada dos tiempos: la figura no cae nunca donde el
        # acorde, y tarda cuatro compases en volver a coincidir.
        hueco = compas / 6.0
        t, paso = inicio, 0
        while t < fin:
            acorde = [x + tr for x in CUARTAS[sec[(int((t - inicio) / (compas * 2)))
                                                  % len(sec)]]]
            celda = plan["notas"]
            if paso % 3 != 2:                     # uno de cada tres, en silencio
                midi = acorde[1 + (paso % celda)] + 12 + plan["octava"]
                fuerte = 0.30 if paso % 6 == 0 else 0.185
                mezclar(pista, madera(nota(midi)), t, fuerte)
            t += hueco
            paso += 1


def mezclar(destino, trozo, inicio, ganancia):
    i = int(inicio * SR)
    n = min(len(trozo), len(destino) - i)
    if n > 0:
        destino[i:i + n] += trozo[:n] * ganancia


def escribir_wav(ruta, pista):
    """Sin dependencias: WAV de 16 bits y listo."""
    datos = np.clip(pista, -1, 1)
    enteros = (datos * 32767).astype("<i2")
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(enteros.tobytes())


def main():
    pal = paleta()
    global COMPAS
    COMPAS = 60.0 / pal["pulso"] * 4
    transporte = pal["transporte"]
    marcas = json.loads((AUDIO / "marcas.json").read_text(encoding="utf-8"))
    total = marcas["total"] + 4
    # dónde empieza cada acto, para que la armonía cambie con el relato
    cortes = {}
    for p in marcas["planos"]:
        cortes.setdefault(p["acto"], p["inicio"])
    actos = sorted(cortes.items())

    n = int(total * SR)
    pista = np.zeros((n, 2))

    if pal.get("motor") == "vacio":
        print(f"· componiendo {total/60:.1f} min · pieza «vacío»", flush=True)
        componer_vacio(pista, actos, total, pal)
        return rematar(pista, n, total)

    print(f"· componiendo {total/60:.1f} min · tono: {TONO}", flush=True)

    for idx, (acto, inicio) in enumerate(actos):
        fin = actos[idx + 1][1] if idx + 1 < len(actos) else total
        plan = PLAN.get(acto, PLAN[1])
        secuencia = plan["acordes"]

        # --- acordes ---------------------------------------------------
        t = inicio
        paso = 0
        while t < fin:
            acorde = [n + transporte for n in ACORDES[secuencia[paso % len(secuencia)]]]
            dur = min(COMPAS * 2, fin - t) + 2.5      # solapan, para que respire
            for grado, midi in enumerate(acorde[1:]):
                voz = cuerda(nota(midi), dur, armonicos=4 if grado < 2 else 3)
                voz *= sobre(len(voz), 2.2, 2.6)[:, None]
                mezclar(pista, voz, t, 0.085 / (1 + grado * 0.35))
            # --- zumbido grave ----------------------------------------
            # Es lo que más "amenaza": en modo sobrio sube una octava y baja
            # de volumen, para que sostenga sin pesar.
            raiz = grave(nota(acorde[0] + plan.get("grave", -12)), dur)
            raiz *= sobre(len(raiz), 2.5, 2.5)[:, None]
            mezclar(pista, raiz, t, 0.16 if plan.get("grave", -12) < 0 else 0.085)
            t += COMPAS * 2
            paso += 1

        # --- el pulso repetido ----------------------------------------
        # Dos notas del acorde alternándose, muy bajas. Suena a algo que
        # está calculando, sin llegar a ser inquietante.
        if pal["ostinato"] > 0.01:
            t, paso = inicio, 0
            while t < fin:
                acorde = [n + transporte for n in ACORDES[secuencia[(paso // 8) % len(secuencia)]]]
                nota_midi = acorde[2 + (paso % 2)]
                mezclar(pista, pizca(nota(nota_midi + 12)), t, 0.055 * pal["ostinato"])
                t += COMPAS / 4
                paso += 1

        # --- pulso -----------------------------------------------------
        if plan["pulso"] > 0.05:
            t = inicio
            while t < fin:
                mezclar(pista, golpe(), t, 0.1 * plan["pulso"])
                t += COMPAS

    return rematar(pista, n, total)


def rematar(pista, n, total):
    print("· añadiendo el aire", flush=True)
    pista += aire(total, 0.7)[:n] * 0.012
    pista *= sobre(n, 3.0, 5.0)[:, None]
    pico = np.max(np.abs(pista))
    pista = pista / pico * 0.5 if pico > 0 else pista

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    escribir_wav(SALIDA, pista)
    rms = 20 * math.log10(np.sqrt(np.mean(pista ** 2)) + 1e-12)
    print(f"· {SALIDA.name}: {total/60:.1f} min · pico −6 dB · medio {rms:.0f} dB",
          flush=True)


if __name__ == "__main__":
    main()
