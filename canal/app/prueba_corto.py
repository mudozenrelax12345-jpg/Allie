"""Comprueba el montaje de un Short sin generar voz.

POR QUÉ ASÍ. Lo que puede salir mal en un Short no es la voz —esa máquina
lleva funcionando desde el primer vídeo— sino el montaje vertical, que es
nuevo: el recorte, el ritmo, los subtítulos y el bucle. Generar la narración
para probarlo cuesta minutos y un modelo de varios cientos de megas, y no
comprueba nada que no estuviera ya comprobado.

Así que aquí la narración se finge: un silencio de la duración que tendría,
con las mismas marcas por frase. Todo lo demás es el montaje de verdad, con
ffmpeg, y al final se MIRA EL FICHERO QUE SALE: cuánto dura, qué tamaño
tiene, cuántos fotogramas. Mirar la salida y no el código es la lección más
cara de este mes.

Lo que se exige, y de dónde sale cada número:

  · Ningún plano por debajo de 1,2s ni por encima de 2,5s. Fuera de esa
    banda la retención cae.
  · NUNCA la misma imagen dos veces seguida. El montaje largo tenía el 33 %
    del metraje así, hasta 15 segundos en la misma foto.
  · El último plano es el primero, para que el bucle no se note.
  · Hay un rótulo en el segundo 0. Entre el 30 y el 50 % de la gente se va
    en los tres primeros segundos y la mayoría lo ve sin sonido.
  · Los rótulos no se pisan ni dejan huecos: cubren la narración entera.
  · El vídeo que sale mide 1080×1920 y dura lo que dura el audio.
"""
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
BASE = APP.parent

import corto  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que + (f" · {detalle}" if detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


def narracion_fingida(frases, destino_wav):
    """Silencio con las marcas que tendría la voz real.

    150 palabras por minuto es el ritmo de Kokoro a velocidad 0,95, que es
    el que lleva el canal.
    """
    marcas, t = [], 0.0
    for texto in frases:
        d = len(texto.split()) / 150 * 60
        marcas.append({"texto": texto, "inicio": round(t, 3), "duracion": round(d, 3)})
        t += d + 0.12
    destino_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino_wav), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * int(24000 * t))
    return marcas, round(t, 3)


def sondear(mp4):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=width,height,nb_read_packets,codec_type:format=duration",
         "-count_packets", "-of", "json", str(mp4)],
        capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def main():
    cortos = corto.cargar()
    comprobar("hay Shorts definidos", len(cortos) >= 1, f"{len(cortos)}")

    # ── 1 · El reparto de planos, para los diez, sin montar nada ───────────
    for c in cortos:
        total = sum(len(l.split()) for l in c["narracion"]) / 150 * 60
        duraciones = corto.repartir(total, c["imagenes"])
        nombres = corto.elegir(c["imagenes"], len(duraciones))

        fuera = [d for d in duraciones if d < 1.2 or d > 2.5]
        comprobar(f"{c['id']}: todos los planos entre 1,2 y 2,5s",
                  not fuera,
                  f"{len(fuera)} fuera: {[round(d,2) for d in fuera][:4]}")

        seguidas = [nombres[i] for i in range(1, len(nombres))
                    if nombres[i] == nombres[i - 1]]
        comprobar(f"{c['id']}: ninguna imagen repetida seguida", not seguidas,
                  f"repetidas: {seguidas[:3]}")

        comprobar(f"{c['id']}: cierra el bucle", nombres[-1] == nombres[0],
                  f"empieza con {nombres[0]} y acaba con {nombres[-1]}")

        comprobar(f"{c['id']}: la suma de planos es la duración",
                  abs(sum(duraciones) - total) < 0.01)

        carpeta = BASE / "videos" / c["de"] / "imagenes"
        perdidas = [n for n in set(nombres) if not (carpeta / f"{n}.jpg").exists()]
        comprobar(f"{c['id']}: están todas las imágenes", not perdidas, str(perdidas))

    # ── 2 · Los rótulos ────────────────────────────────────────────────────
    c = cortos[0]
    marcas, total = narracion_fingida(c["narracion"], corto.TRABAJO / "prueba.wav")
    rotulos = []
    for m in marcas:
        rotulos.extend(corto.trocear_frase(m["texto"], m["inicio"], m["duracion"]))

    comprobar("hay un rótulo en el segundo 0", rotulos[0]["inicio"] < 0.01,
              f"el primero entra en {rotulos[0]['inicio']}s")
    comprobar("ningún rótulo pasa de cuatro palabras",
              all(len(r["texto"].split()) <= 4 for r in rotulos))

    # Ninguno cruza un punto: «APARTMENTS. KEPT» salió así en el primer
    # montaje y se lee como un trabalenguas.
    cruzan = [r["texto"] for r in rotulos
              if re.search(r"[.!?;:]\s+\S", r["texto"])]
    comprobar("ningún rótulo cruza un punto", not cruzan, str(cruzan[:3]))

    # Y ninguno se sale de la pantalla: es el fallo que la primera versión
    # pasó entera sin que ninguna comprobación lo viera. Solo se vio
    # mirando el fotograma.
    from PIL import ImageFont
    anchos = []
    for r in rotulos:
        cuerpo = corto.encaje(r["texto"])
        f = ImageFont.truetype(corto.FUENTE, cuerpo)
        anchos.append((r["texto"], f.getbbox(r["texto"].upper())[2]))
    salidos = [(t, a) for t, a in anchos if a > corto.ANCHO_ROTULO]
    comprobar("ningún rótulo se sale de la pantalla", not salidos,
              f"el más ancho mide {max(a for _, a in anchos)}px "
              f"de {corto.ANCHO_ROTULO} · {salidos[:2]}")
    solapes = [i for i in range(1, len(rotulos))
               if rotulos[i]["inicio"] + 0.001 < rotulos[i - 1]["inicio"] + rotulos[i - 1]["duracion"]]
    comprobar("los rótulos no se pisan", not solapes, f"{len(solapes)} solapes")
    cubierto = sum(r["duracion"] for r in rotulos)
    hablado = sum(m["duracion"] for m in marcas)
    comprobar("los rótulos cubren toda la narración",
              abs(cubierto - hablado) < 0.05, f"{cubierto:.2f}s de {hablado:.2f}s")
    con_cifra = [r for r in rotulos
                 if any(p in r["texto"].lower() for p in ("thousand", "percent", "three"))]
    comprobar("las cifras se reconocen para pintarlas en ámbar", len(con_cifra) >= 1,
              f"{len(con_cifra)} rótulos con cifra")

    # El fichero ASS tiene que ser legible para libass.
    ass = corto.subtitulos(rotulos, corto.TRABAJO / "prueba.ass")
    t = ass.read_text(encoding="utf-8")
    comprobar("el ASS lleva la resolución del Short",
              f"PlayResX: {corto.W}" in t and f"PlayResY: {corto.H}" in t)
    comprobar("el ASS no deja llaves sueltas que rompan el formato",
              t.count("{") == t.count("}"))

    # ── 3 · Montar uno de verdad y MIRAR EL FICHERO ───────────────────────
    print("\n--- montando uno de verdad para mirarlo", flush=True)
    # A una carpeta temporal, NO a cortos/salida. La primera vez el prueba.mp4
    # acabó en el artefacto y publicado junto a los diez de verdad, porque el
    # flujo recoge todo lo que hay en salida/. Una prueba que escribe en la
    # carpeta de producción no es una prueba: es un Short más.
    import tempfile
    destino = Path(tempfile.mkdtemp()) / "prueba.mp4"
    planos, n_rotulos = corto.montar(c, marcas, total,
                                     corto.TRABAJO / "prueba.wav", destino)
    comprobar("el fichero existe", destino.exists())

    s = sondear(destino)
    v = next((x for x in s.get("streams", []) if x.get("codec_type") == "video"), {})
    a = next((x for x in s.get("streams", []) if x.get("codec_type") == "audio"), {})
    dur = float(s.get("format", {}).get("duration", 0))
    comprobar("mide 1080×1920", (v.get("width"), v.get("height")) == (corto.W, corto.H),
              f"{v.get('width')}×{v.get('height')}")
    comprobar("dura lo que la narración", abs(dur - total) < 1.0,
              f"{dur:.1f}s frente a {total:.1f}s")
    comprobar("un Short no pasa de 60s", dur <= 60, f"{dur:.1f}s")
    comprobar("lleva audio", bool(a))
    comprobar("el ritmo sale a menos de 2,5s por plano", dur / planos < 2.5,
              f"{dur / planos:.2f}s por plano · {planos} planos")

    # Que los subtítulos estén QUEMADOS, no solo generados: se comparan dos
    # fotogramas de la zona del rótulo. Si el ASS no se aplicó, son iguales.
    import hashlib
    trozos = []
    for seg in (0.6, 2.4):
        p = corto.TRABAJO / f"f{seg}.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(seg),
                        "-i", str(destino), "-frames:v", "1",
                        "-vf", f"crop={corto.W}:300:0:{corto.SUB_Y - 150}", str(p)],
                       capture_output=True)
        trozos.append(hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else "")
    comprobar("los subtítulos están quemados en la imagen",
              trozos[0] and trozos[0] != trozos[1],
              "dos fotogramas distintos en la banda del rótulo")

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print(f"\nel taller de Shorts funciona · {destino}", flush=True)


if __name__ == "__main__":
    main()
