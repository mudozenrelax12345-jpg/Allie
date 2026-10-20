"""Coloca los efectos de sonido leyendo el propio montaje.

No se ponen a ojo: el montaje deja escrito en qué segundo entra cada cartel,
cada cifra y cada documento, y aquí se usan esas marcas. Por construcción
están sincronizados al fotograma.

Qué suena y cuándo:

  cartel de capítulo   una subida de 2 s que termina justo en el corte,
                       y un golpe grave al entrar
  cifra grande         un golpe seco. No es un susto, es un punto final
  documento            un roce de papel: el sonido de «aquí hay una prueba»
  rótulo               un tic finísimo, muy agudo, fuera del rango de la voz
  frase de remate      la música se calla un segundo antes y vuelve después

Lo que NO hay, a propósito: ruido de túnel de lavado, caja registradora,
golpes de terror. Eso es lo que hace el contenido conspiranoico y le quita
credibilidad justo a la parte que más la necesita.

  musica/fondo.wav     música con sus silencios + efectos, listo para mezclar
"""
import json
import wave
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
LECHO = BASE / "musica" / "lecho.wav"
SALIDA = BASE / "musica" / "fondo.wav"
PLANOS = BASE / "video" / "planos.json"

SR = 44100
RNG = np.random.default_rng(11)

AJUSTES = BASE / "video" / "sonido.json"

# Qué tarjetas llevan golpe y en cuáles se calla la música lo dice el
# montaje de cada vídeo, en la sección «sonido:» de su montaje.yml.
#   golpes:    las cifras que merecen un punto final. Si todo se subraya,
#              no se subraya nada.
#   silencios: cinco en diez minutos. Más, y deja de notarse.
def ajustes():
    if AJUSTES.exists():
        d = json.loads(AJUSTES.read_text(encoding="utf-8"))
        return set(d.get("golpes", [])), set(d.get("silencios", []))
    return set(), set()


def leer_wav(ruta):
    with wave.open(str(ruta), "rb") as w:
        n, canales = w.getnframes(), w.getnchannels()
        crudo = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32767
    return crudo.reshape(-1, canales) if canales > 1 else np.stack([crudo] * 2, 1)


def escribir_wav(ruta, pista):
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(pista, -1, 1) * 32767).astype("<i2").tobytes())


def est(mono):
    return np.stack([mono, mono], axis=1)


def suave(mono, fuerza=0.02):
    """Paso bajo de un polo. Quita el filo digital de los sintéticos."""
    salida = np.empty_like(mono)
    acc = 0.0
    for i, v in enumerate(mono):
        acc += fuerza * (v - acc)
        salida[i] = acc
    return salida


def agudo(mono, fuerza=0.02):
    return mono - suave(mono, fuerza)


# ------------------------------------------------------------------ cues
def impacto(fuerza=1.0):
    """Golpe grave y corto. Todo por debajo de la voz, así que no estorba."""
    dur = 1.5
    t = np.linspace(0, dur, int(dur * SR), endpoint=False)
    caida = np.exp(-t * 4.5)
    # la frecuencia baja al golpear: eso es lo que lo hace sonar a «peso»
    f = 48 * np.exp(-t * 6) + 33
    cuerpo = np.sin(2 * np.pi * np.cumsum(f) / SR) * caida
    chasquido = suave(RNG.normal(0, 1, len(t)), 0.05) * np.exp(-t * 60) * 0.25
    return est((cuerpo + chasquido) * 0.9 * fuerza)


def subida(dur=2.0):
    """Swell de 2 s que remata justo en el corte. Avisa de que algo cambia."""
    t = np.linspace(0, dur, int(dur * SR), endpoint=False)
    rampa = (t / dur) ** 2.2
    ruido = agudo(suave(RNG.normal(0, 1, len(t)), 0.25), 0.004)
    tono = np.sin(2 * np.pi * (180 + 320 * rampa) * t) * 0.25
    mezcla = (ruido * 0.5 + tono) * rampa
    mezcla[-int(0.05 * SR):] *= np.linspace(1, 0, int(0.05 * SR))
    return est(mezcla * 0.5)


def papel():
    """Roce de folios. Dos movimientos, no uno: así suena a mano, no a ruido."""
    dur = 0.75
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    ruido = agudo(RNG.normal(0, 1, n), 0.06)
    env = (np.exp(-((t - 0.07) / 0.045) ** 2) * 1.0
           + np.exp(-((t - 0.30) / 0.075) ** 2) * 0.75
           + np.exp(-((t - 0.52) / 0.06) ** 2) * 0.45)
    return est(ruido * env * 0.33)


def tic():
    """Tic de 25 ms, muy agudo. Vive por encima de la voz, no la pisa."""
    n = int(0.03 * SR)
    t = np.linspace(0, 0.03, n, endpoint=False)
    s = np.sin(2 * np.pi * 5200 * t) * np.exp(-t * 180)
    return est(s * 0.12)


def mezclar(destino, trozo, inicio, ganancia=1.0):
    i = max(0, int(inicio * SR))
    n = min(len(trozo), len(destino) - i)
    if n > 0:
        destino[i:i + n] += trozo[:n] * ganancia


def rampa_baja(pista, inicio, dur, hondo=0.12, borde=0.35):
    """Agacha la música un momento. El silencio antes de una frase es el
    recurso más potente que hay, y es gratis."""
    i, n = int(inicio * SR), int(dur * SR)
    i = max(0, min(i, len(pista) - 1))
    n = min(n, len(pista) - i)
    if n <= 0:
        return
    b = min(int(borde * SR), n // 2)
    env = np.full(n, hondo)
    if b:
        env[:b] = np.linspace(1, hondo, b)
        env[-b:] = np.linspace(hondo, 1, b)
    pista[i:i + n] *= env[:, None]


# ------------------------------------------------------------------ main
def main():
    if not PLANOS.exists():
        print("· sin video/planos.json: no coloco efectos", flush=True)
        return
    planos = json.loads(PLANOS.read_text(encoding="utf-8"))
    musica = leer_wav(LECHO) if LECHO.exists() else None
    total = planos[-1]["inicio"] + planos[-1]["duracion"] + 2
    n = int(total * SR)
    if musica is None:
        musica = np.zeros((n, 2))
    elif len(musica) < n:
        musica = np.vstack([musica, np.zeros((n - len(musica), 2))])
    else:
        musica = musica[:n]

    CIFRAS, SILENCIO = ajustes()
    efectos = np.zeros((n, 2))
    cuenta = {"golpe": 0, "subida": 0, "papel": 0, "tic": 0, "silencio": 0}

    for p in planos:
        t, nombre = p["inicio"], (p.get("material") or "")

        if nombre.startswith("C") and len(nombre) == 2:          # cartel de acto
            mezclar(efectos, subida(2.0), t - 2.0)
            mezclar(efectos, impacto(0.85), t)
            rampa_baja(musica, t - 1.6, 2.4, hondo=0.25)
            cuenta["subida"] += 1
            cuenta["golpe"] += 1

        elif nombre in CIFRAS:
            mezclar(efectos, impacto(0.7), t)
            cuenta["golpe"] += 1

        elif nombre.startswith("DOC"):
            mezclar(efectos, papel(), t)
            cuenta["papel"] += 1

        if p.get("rotulo"):
            mezclar(efectos, tic(), t + 0.12)
            cuenta["tic"] += 1

        # Las frases de remate entran en seco: la música se aparta justo
        # antes y vuelve en cuanto termina la idea.
        if nombre in SILENCIO:
            rampa_baja(musica, t - 1.0, p["duracion"] + 1.4, hondo=0.07, borde=0.5)
            cuenta["silencio"] += 1
        elif p.get("remate"):
            rampa_baja(musica, t - 0.5, p["duracion"] + 0.8, hondo=0.42)

    fondo = musica + efectos
    pico = np.max(np.abs(fondo))
    if pico > 0.95:
        fondo *= 0.95 / pico
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    escribir_wav(SALIDA, fondo)
    print(f"· efectos colocados: {cuenta['golpe']} golpes · {cuenta['subida']} subidas · "
          f"{cuenta['papel']} papeles · {cuenta['tic']} tics · "
          f"{cuenta['silencio']} silencios", flush=True)


if __name__ == "__main__":
    main()
