"""Una base musical sintetizada aquí mismo, sin descargar nada.

POR QUÉ HAY QUE PONER MÚSICA. Los vídeos que iba entregando llevaban voz
sobre SILENCIO ABSOLUTO. En TikTok eso suena a fallo: no hay un solo vídeo
que funcione sin una base por debajo, y un vídeo mudo con una voz encima
se percibe como algo roto antes incluso de entender de qué va.

POR QUÉ SINTETIZADA Y NO DESCARGADA. Las pistas «libres de derechos» de
internet casi nunca lo son del todo: la mayoría son CC BY-SA —que obligaría
a publicar el vídeo entero con esa licencia— o piden atribución en
condiciones que cambian según el sitio. Y las bibliotecas de TikTok e
Instagram solo valen dentro de sus aplicaciones. Esto es aritmética: no hay
obra de nadie, así que no hay licencia que cumplir.

QUÉ SUENA. Teresa: «música de fondo bonita». La versión vieja era un beat
seco de cuatro senos. Esta es un lo-fi cálido: notas de piano (varios
armónicos que decaen, como una cuerda al pulsarse), acordes con séptima que
suenan a jazz suave, un arpegio por encima, un bajo redondo y una batería
muy floja. Más lento (78 pulsos) para que respire, con unas reflexiones
tempranas que dan sensación de sala y un filtro que le quita el filo digital.

CÓMO SE MEZCLA. La base va MUY por debajo: la voz manda. En el montaje se
baja diez decibelios respecto a la voz; por encima de eso se come las
consonantes y el dato deja de entenderse.
"""
import numpy as np

FREC = 24000
BPM = 78


# ───────────────────────────────────────────── notas
def _env_adsr(n, ataque, decaimiento, sostiene, suelta):
    """Envolvente con ataque, caída, sostenido y suelta."""
    e = np.zeros(n)
    a = min(n, max(1, int(ataque * FREC)))
    d = max(1, int(decaimiento * FREC))
    s = max(1, int(suelta * FREC))
    e[:a] = np.linspace(0, 1, a)
    fin_d = min(n, a + d)
    if fin_d > a:
        e[a:fin_d] = np.linspace(1, sostiene, fin_d - a)
    if fin_d < n:
        e[fin_d:] = sostiene
    if s < n:
        e[-s:] *= np.linspace(1, 0, s)
    return e


def _piano(frec, dur, vol=1.0):
    """Una nota con cuerpo de piano: varios armónicos que decaen distinto.

    No es un piano de verdad, pero suma de senos con decaimiento exponencial
    por armónico suena a cuerda pulsada y no a pitido.
    """
    n = int(dur * FREC)
    t = np.arange(n) / FREC
    o = np.zeros(n)
    # armónico: (múltiplo, peso, rapidez de caída)
    for mult, peso, caida in ((1, 1.0, 1.6), (2, 0.5, 2.4),
                              (3, 0.28, 3.2), (4, 0.14, 4.5), (6, 0.07, 6.0)):
        o += peso * np.sin(2 * np.pi * frec * mult * t) * np.exp(-t * caida)
    o *= _env_adsr(n, 0.004, dur * 0.9, 0.0, min(0.05, dur * 0.2))
    return o * vol


def _pad(frec, dur, vol=1.0):
    """Un colchón suave y sostenido, con dos osciladores ligeramente
    desafinados para que respire."""
    n = int(dur * FREC)
    t = np.arange(n) / FREC
    o = (np.sin(2 * np.pi * frec * t)
         + np.sin(2 * np.pi * frec * 1.003 * t)
         + 0.5 * np.sin(2 * np.pi * frec * 2 * t))
    return o * _env_adsr(n, 0.12, dur, 0.85, min(0.3, dur * 0.4)) * vol


def _bombo(dur=0.22):
    n = int(dur * FREC)
    t = np.arange(n) / FREC
    f = 95 * np.exp(-t * 26) + 42
    o = np.sin(2 * np.pi * np.cumsum(f) / FREC)
    return o * _env_adsr(n, 0.002, dur, 0.0, dur * 0.7)


def _charles(dur=0.06):
    n = int(dur * FREC)
    r = np.random.default_rng(7).standard_normal(n)
    r = r - np.convolve(r, np.ones(16) / 16, mode="same")   # quitar graves
    return r * _env_adsr(n, 0.001, dur, 0.0, dur * 0.9) * 0.2


# ───────────────────────────────────────────── acordes
# Frecuencias (Hz) de las notas que uso, afinación estándar.
_N = {"C2": 65.41, "E2": 82.41, "F2": 87.31, "G2": 98.00, "A2": 110.00,
      "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61, "G3": 196.00,
      "A3": 220.00, "B3": 246.94,
      "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00,
      "A4": 440.00, "B4": 493.88, "C5": 523.25, "D5": 587.33, "E5": 659.25}

# Progresión cálida en Do: Cmaj7 · Am7 · Fmaj7 · G7. No cansa y suena dulce.
_PROG = [
    ("C2", ["C4", "E4", "G4", "B4"]),
    ("A2", ["C4", "E4", "G4", "A4"]),
    ("F2", ["C4", "F4", "A4", "E4"]),
    ("G2", ["D4", "F4", "G4", "B4"]),
]


def _reverb(x, mezcla=0.28):
    """Reflexiones tempranas: unas copias retrasadas y flojas dan sala.

    Sin IIR (que necesitaría scipy): se suman unos ecos finitos, que es
    barato y suficiente para quitar la sensación de estudio seco.
    """
    retardos = [(0.017, 0.5), (0.031, 0.38), (0.053, 0.28),
                (0.079, 0.2), (0.113, 0.13)]
    y = x.copy()
    for seg, g in retardos:
        d = int(seg * FREC)
        eco = np.zeros_like(x)
        eco[d:] = x[:-d] * g
        y += eco * mezcla
    return y


def _suaviza(x, taps=9):
    """Filtro paso-bajo sencillo: redondea el agudo digital, da calidez."""
    return np.convolve(x, np.ones(taps) / taps, mode="same")


def base(segundos, semilla=3):
    """Una base lo-fi cálida de la duración que haga falta."""
    rng = np.random.default_rng(semilla)
    pulso = 60.0 / BPM
    compas = pulso * 4
    n_compas = int(compas * FREC)

    bloques = []
    for bi, (bajo, acorde) in enumerate(_PROG):
        b = np.zeros(n_compas + FREC)   # cola para que el reverb no se corte

        # bajo: dos notas redondas por compás
        for k in (0.0, 2.0):
            x = _piano(_N[bajo], pulso * 2.1, 0.5)
            p = int(k * pulso * FREC)
            b[p:p + len(x)] += x

        # pad del acorde, muy suave, todo el compás
        for nota in acorde:
            x = _pad(_N[nota] / 2, compas * 0.98, 0.05)   # una octava abajo
            b[:len(x)] += x

        # arpegio de piano: las notas del acorde en corcheas, suave
        patron = [0, 1, 2, 3, 2, 1, 2, 3]
        for j, idx in enumerate(patron):
            nota = acorde[idx % len(acorde)]
            dur = pulso * 0.5
            x = _piano(_N[nota], dur * 1.8, 0.16 + 0.03 * rng.random())
            p = int(j * dur * FREC)
            b[p:p + len(x)] += x

        # batería muy floja: bombo en 1 y 3, charles en las corcheas impares
        for k in (0.0, 2.0):
            g = _bombo()
            p = int(k * pulso * FREC)
            b[p:p + len(g)] += g * 0.45
        for k in (0.5, 1.5, 2.5, 3.5):
            g = _charles()
            p = int(k * pulso * FREC)
            b[p:p + len(g)] += g * 0.5

        bloques.append(b * (0.97 + 0.03 * rng.random()))

    # Encadenar los compases solapando la cola de reverb de cada uno.
    pista = np.zeros(int(len(_PROG) * compas * FREC) + FREC)
    for bi, b in enumerate(bloques):
        p = int(bi * compas * FREC)
        pista[p:p + len(b)] += b
    loop = pista[:int(len(_PROG) * compas * FREC)]

    # Repetir hasta cubrir y recortar.
    repes = int(np.ceil(segundos * FREC / len(loop)))
    pista = np.tile(loop, max(1, repes))[:int(segundos * FREC)]

    pista = _reverb(pista)
    pista = _suaviza(pista)
    pico = np.max(np.abs(pista)) or 1.0
    pista = pista / pico * 0.6

    # Entrada y salida suaves.
    s = int(1.0 * FREC)
    if len(pista) > 2 * s:
        pista[:s] *= np.linspace(0, 1, s)
        pista[-s:] *= np.linspace(1, 0, s)
    return pista.astype(np.float32)


def escribir(destino, segundos):
    """Sin dependencias: el módulo wave viene con Python."""
    import wave
    a = np.clip(base(segundos), -1.0, 1.0)
    with wave.open(str(destino), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FREC)
        w.writeframes((a * 32767).astype("<i2").tobytes())
    return destino


if __name__ == "__main__":
    import sys
    escribir(sys.argv[1] if len(sys.argv) > 1 else "/tmp/base.wav",
             float(sys.argv[2]) if len(sys.argv) > 2 else 24.0)
    print("listo")
