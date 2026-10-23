"""Una base musical sintetizada aquí mismo, sin descargar nada.

POR QUÉ HAY QUE PONER MÚSICA. Los vídeos que iba entregando llevaban voz
sobre SILENCIO ABSOLUTO. En TikTok eso suena a fallo: no hay un solo vídeo
que funcione sin una base por debajo, y un vídeo mudo con una voz encima
se percibe como algo roto antes incluso de entender de qué va.

POR QUÉ SINTETIZADA Y NO DESCARGADA. Las pistas «libres de derechos» de
internet casi nunca lo son del todo: la mayoría son CC BY-SA —que obligaría
a publicar el vídeo entero con esa licencia— o piden atribución en
condiciones que cambian según el sitio. Y las bibliotecas de TikTok e
Instagram solo valen dentro de sus aplicaciones, así que un vídeo con esa
música no se puede cruzar de una red a otra.

Esto se genera con cuatro senos y un poco de ruido. No hay licencia que
cumplir porque no hay obra de nadie: es aritmética. Ocupa cero y suena
discreto, que es lo único que se le pide a una base que va por debajo de
una voz.

CÓMO SE MEZCLA. La base va MUY por debajo: la voz manda. Se mezcla a -26 dB
contra los -16 de la voz, que son diez decibelios de diferencia; por encima
de eso la base empieza a comerse las consonantes y el dato deja de
entenderse, que es justo lo contrario de lo que se busca.
"""
import numpy as np

FREC = 24000
BPM = 92


def _env(n, ataque, caida):
    """Una envolvente de volumen: sube rápido y cae."""
    e = np.ones(n)
    a = max(1, int(ataque * FREC))
    c = max(1, int(caida * FREC))
    e[:a] = np.linspace(0, 1, a)
    if c < n:
        e[-c:] = np.linspace(1, 0, c)
    return e


def _nota(frec, dur, forma="seno", vol=1.0):
    n = int(dur * FREC)
    t = np.arange(n) / FREC
    if forma == "seno":
        o = np.sin(2 * np.pi * frec * t)
    elif forma == "triangulo":
        o = 2 * np.abs(2 * ((t * frec) % 1) - 1) - 1
    else:
        o = np.sign(np.sin(2 * np.pi * frec * t)) * 0.5
    return o * _env(n, 0.01, min(dur * 0.6, 0.25)) * vol


def _bombo(dur=0.16):
    """Un golpe grave: un seno que baja de 110 a 45 hercios."""
    n = int(dur * FREC)
    t = np.arange(n) / FREC
    f = 110 * np.exp(-t * 22) + 45
    return np.sin(2 * np.pi * np.cumsum(f) / FREC) * _env(n, 0.002, dur * 0.8)


def _charles(dur=0.05):
    """Ruido breve y agudo."""
    n = int(dur * FREC)
    r = np.random.default_rng(7).standard_normal(n)
    r = r - np.convolve(r, np.ones(12) / 12, mode="same")   # quitar los graves
    return r * _env(n, 0.001, dur * 0.9) * 0.25


def base(segundos, semilla=3):
    """Una base instrumental de la duración que haga falta.

    Un compás de cuatro tiempos con bombo, charles y un bajo que recorre
    cuatro acordes en menor. Se repite y se corta a medida.
    """
    rng = np.random.default_rng(semilla)
    tiempo = 60.0 / BPM
    compas = tiempo * 4
    n_compas = int(compas * FREC)

    # La menor: La, Fa, Do, Sol. Cuatro acordes que no cansan.
    raices = [110.00, 87.31, 130.81, 98.00]
    bloques = []
    for i, raiz in enumerate(raices):
        b = np.zeros(n_compas)
        # bajo, dos notas largas por compás
        for k in (0, 2):
            x = _nota(raiz, tiempo * 1.9, "triangulo", 0.42)
            p = int(k * tiempo * FREC)
            b[p:p + len(x)] += x[:max(0, len(b) - p)]
        # un acorde suave por encima, en la octava de arriba
        for mult, vol in ((2.0, 0.10), (2.5, 0.07), (3.0, 0.05)):
            x = _nota(raiz * mult, compas * 0.92, "seno", vol)
            b[:len(x)] += x[:len(b)]
        # percusión
        for k in (0, 1, 2, 3):
            g = _bombo() if k in (0, 2) else _charles()
            p = int(k * tiempo * FREC)
            b[p:p + len(g)] += g[:max(0, len(b) - p)] * (0.5 if k in (0, 2) else 1.0)
        for k in (0.5, 1.5, 2.5, 3.5):
            g = _charles()
            p = int(k * tiempo * FREC)
            b[p:p + len(g)] += g[:max(0, len(b) - p)] * 0.6
        bloques.append(b * (0.95 + 0.05 * rng.random()))

    pista = np.concatenate(bloques)
    repes = int(np.ceil(segundos * FREC / len(pista)))
    pista = np.tile(pista, max(1, repes))[:int(segundos * FREC)]

    # Suavizar: un filtro de media móvil quita el filo digital.
    pista = np.convolve(pista, np.ones(7) / 7, mode="same")
    pico = np.max(np.abs(pista)) or 1.0
    pista = pista / pico * 0.6

    # Entrada y salida, para que no empiece ni acabe de golpe.
    s = int(0.8 * FREC)
    if len(pista) > 2 * s:
        pista[:s] *= np.linspace(0, 1, s)
        pista[-s:] *= np.linspace(1, 0, s)
    return pista.astype(np.float32)


def escribir(destino, segundos):
    """Sin dependencias: el módulo wave viene con Python.

    Estaba escrito con soundfile y aquí no se puede instalar, así que la
    base no se podía ni escuchar en local. Una pieza que solo se puede
    probar en la máquina de GitHub es una pieza que se rompe sin avisar;
    ya pasó con la rama de voz el 22 de octubre.
    """
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
