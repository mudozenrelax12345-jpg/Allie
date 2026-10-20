"""Convierte un guion en pistas de audio listas para el montaje.

Lee un archivo de guion en Markdown, saca solo las líneas de narración (las que
empiezan por "> "), las agrupa por acto (los "### Acto …") y genera:

  audio/01-el-gancho.wav      un archivo por acto
  audio/completo.wav          todo seguido, con pausas entre actos
  audio/marcas.txt            en qué minuto empieza cada acto y cada párrafo

Las marcas son lo que de verdad ahorra tiempo: al montar, sabes exactamente
dónde cae cada frase sin tener que buscarla a oído.
"""
import json
import os
import re
import sys
import unicodedata
import wave
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "audio"

VOZ = os.environ.get("KOKORO_VOZ", "af_heart")
VELOCIDAD = float(os.environ.get("KOKORO_VELOCIDAD", "1.0"))
FRECUENCIA = 24000
PAUSA_PARRAFO = 0.6      # segundos de silencio entre párrafos
PAUSA_ACTO = 1.6         # entre actos
PAUSA_FRASE = 0.10       # entre frases dentro de un mismo párrafo


# Abreviaturas detrás de las cuales un punto NO termina la frase.
NO_CORTA = r"(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bSt)(?<!\bNo)(?<!\bvs)(?<![A-Z])"


def frases_de(parrafo):
    """Parte un párrafo en frases.

    Hasta ahora la voz se generaba párrafo entero, así que el montaje sabía
    cuándo empezaba un bloque de veinte segundos pero no cuándo se decía cada
    frase dentro de él. De ahí que el texto en pantalla fuera por detrás o por
    delante de lo que se oía. Generando frase a frase, el segundo de cada una
    se sabe por construcción, sin estimar nada.
    """
    trozos = re.split(rf"{NO_CORTA}(?<=[.!?])\s+", parrafo.strip())
    return [t.strip() for t in trozos if t.strip()]


def log(m):
    print(f"· {m}", flush=True)


# ------------------------------------------------------------------ el guion
def nombre_archivo(texto, n):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return f"{n:02d}-{t[:40] or 'acto'}"


def leer_guion(ruta):
    """Devuelve [(titulo_del_acto, [parrafos])]. Ignora todo lo que no sea narración."""
    actos, titulo, parrafos = [], None, []
    dentro = False
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        cab = re.match(r"^###\s+(.*)$", linea.strip())
        if cab:
            if titulo and parrafos:
                actos.append((titulo, parrafos))
            crudo = cab.group(1).strip()
            # Solo nos interesan los "### Acto N · Lo que sea"
            if crudo.lower().startswith("acto"):
                titulo, parrafos, dentro = crudo, [], True
            else:
                titulo, parrafos, dentro = None, [], False
            continue
        if not dentro:
            continue
        cita = re.match(r"^>\s?(.*)$", linea.rstrip())
        if cita:
            texto = cita.group(1).strip()
            if texto:
                parrafos.append(limpiar(texto))
    if titulo and parrafos:
        actos.append((titulo, parrafos))
    return actos


def limpiar(t):
    """Quita el formato de Markdown: lo que queda es lo que se lee en alto."""
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)   # enlaces
    t = re.sub(r"[*_`]+", "", t)                      # negritas y cursivas
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# -------------------------------------------------------------------- audio
def motor():
    from kokoro import KPipeline
    return KPipeline(lang_code="a")        # inglés americano


def sintetizar(pipeline, texto):
    import numpy as np
    trozos = [a for _, _, a in pipeline(texto, voice=VOZ, speed=VELOCIDAD)]
    if not trozos:
        raise RuntimeError(f"Kokoro no devolvió audio para: {texto[:60]}…")
    return np.concatenate(trozos)


def silencio(segundos):
    import numpy as np
    return np.zeros(int(FRECUENCIA * segundos), dtype="float32")


def guardar(ruta, audio):
    import soundfile as sf
    ruta.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(ruta), audio, FRECUENCIA)


def reloj(segundos):
    m, s = divmod(segundos, 60)
    return f"{int(m):02d}:{s:05.2f}"


# --------------------------------------------------------------------- main
def main():
    import numpy as np

    import config
    guion = sys.argv[1] if len(sys.argv) > 1 else (str(config.guion() or ""))
    if not guion:
        candidatos = sorted((BASE / "guiones").glob("*.md"))
        if not candidatos:
            sys.exit("No hay ningún guion en guiones/.")
        guion = str(candidatos[0])
    log(f"Guion: {Path(guion).name}")

    actos = leer_guion(guion)
    if not actos:
        sys.exit("No he encontrado narración. Las líneas habladas tienen que "
                 "empezar por '> ' y estar bajo un título '### Acto …'.")
    total_parrafos = sum(len(p) for _, p in actos)
    palabras = sum(len(x.split()) for _, p in actos for x in p)
    log(f"{len(actos)} actos · {total_parrafos} párrafos · {palabras} palabras "
        f"(unos {palabras / 150:.0f} min de narración)")

    pipeline = motor()
    completo, marcas, mapa, t = [], [], [], 0.0

    for n, (titulo, parrafos) in enumerate(actos, 1):
        log(f"[{n}/{len(actos)}] {titulo}")
        pista = []
        marcas.append(f"\n{reloj(t)}  ═══ {titulo}")
        for i, texto in enumerate(parrafos):
            marcas.append(f"{reloj(t)}      {texto[:70]}…")
            inicio_parrafo, frases = t, []
            trozos = frases_de(texto)
            for j, frase in enumerate(trozos):
                audio = sintetizar(pipeline, frase)
                d = len(audio) / FRECUENCIA
                frases.append({"texto": frase, "inicio": round(t, 3),
                               "duracion": round(d, 3)})
                pista.append(audio)
                t += d
                if j < len(trozos) - 1:
                    pista.append(silencio(PAUSA_FRASE))
                    t += PAUSA_FRASE
            dur = t - inicio_parrafo
            mapa.append({"acto": n, "parrafo": i + 1, "inicio": round(inicio_parrafo, 3),
                         "duracion": round(dur, 3), "texto": texto,
                         "frases": frases})
            if i < len(parrafos) - 1:
                pista.append(silencio(PAUSA_PARRAFO))
                t += PAUSA_PARRAFO
        pista = np.concatenate(pista)
        guardar(SALIDA / f"{nombre_archivo(titulo, n)}.wav", pista)
        completo.append(pista)
        if n < len(actos):
            completo.append(silencio(PAUSA_ACTO))
            t += PAUSA_ACTO

    guardar(SALIDA / "completo.wav", np.concatenate(completo))
    # Las pausas entre párrafos y actos se reparten en el plano anterior,
    # para que el montaje no deje huecos.
    for k, m in enumerate(mapa):
        fin_siguiente = mapa[k + 1]["inicio"] if k + 1 < len(mapa) else t
        m["duracion"] = round(fin_siguiente - m["inicio"], 3)
    (SALIDA / "marcas.json").write_text(
        json.dumps({"total": round(t, 3), "planos": mapa}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    (SALIDA / "marcas.txt").write_text(
        f"Marcas de tiempo · {Path(guion).name}\n"
        f"Voz: {VOZ} · velocidad: {VELOCIDAD}\n"
        + "\n".join(marcas) + "\n", encoding="utf-8")
    log(f"Listo: {reloj(t)} de narración en {SALIDA.name}/")


if __name__ == "__main__":
    main()
