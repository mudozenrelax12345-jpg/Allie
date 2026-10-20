"""Monta un Short vertical a partir de un guion corto y las imágenes ya hechas.

POR QUÉ ESTE PROGRAMA. El canal tenía tres vídeos largos y veinticinco
visualizaciones. El problema no era lo escrito: era que un vídeo largo de un
canal con seis suscriptores no se le enseña a nadie. Un Short entra en un
feed de desconocidos desde el primer día, y en el nicho de empresa mezclar
Shorts sube el crecimiento de suscriptores alrededor de un 39 %.

LO QUE HACE DISTINTO AL VÍDEO LARGO, y por qué cada decisión:

  1. VERTICAL SIN DESTROZAR LA IMAGEN. Las imágenes son 1920×1080. Recortar
     un 9:16 de ahí deja una tira de 607 píxeles de ancho: se pierde tres
     cuartas partes del encuadre y lo que queda sale blando. Así que la
     imagen va entera, a todo el ancho, sobre una copia de sí misma
     desenfocada y oscurecida que rellena la pantalla. Además deja libre el
     tercio inferior, que es donde tienen que ir los subtítulos.

  2. UN PLANO CADA 1,5-2 SEGUNDOS. Por debajo de 1,2 el ojo deja de
     seguirlo; por encima de 2,5 la retención baja. El vídeo largo iba a
     6,1 segundos de media y con un 33 % del metraje en imágenes repetidas:
     eso aquí no puede pasar, y hay una regla que lo impide.

  3. NUNCA LA MISMA IMAGEN SEGUIDA. Ni una sola vez. Es la regla que el
     montaje largo se saltaba.

  4. SUBTÍTULOS DESDE EL PRIMER FOTOGRAMA. Suben la retención sin sonido
     entre un 25 y un 40 %, y la mayoría de la gente lo ve en silencio.
     De dos a tres palabras por rótulo. Las cifras salen en ámbar, que es
     lo que de verdad se viene a ver.

  5. BUCLE. El último plano es el primero. Desde 2025 cada bucle cuenta
     como visualización nueva, así que un corte que no se nota son vistas.

CÓMO SE SABE CUÁNDO SALE CADA PALABRA. La narración se genera frase a frase,
así que el segundo en que empieza cada frase es exacto. Dentro de la frase,
el reparto entre rótulos se hace por número de caracteres. No es alineación
real —para eso haría falta otro modelo— pero el error es de una décima y a
esa escala no se ve. Lo que sí se vería, y por eso no se hace, es estimar
también el principio de la frase.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

BASE = Path(__file__).resolve().parent.parent
DEFINICIONES = BASE / "cortos" / "cortos.yml"
SALIDA = BASE / "cortos" / "salida"
TRABAJO = BASE / "cortos" / "trozos"

W, H, FPS = 1080, 1920, 30

# El ritmo. Se alterna para que no suene a metrónomo, pero sin salirse nunca
# de la banda que aguanta la atención.
PLANO_MIN, PLANO_MAX = 1.5, 2.1
VAIVEN = [0.94, 1.08, 0.88, 1.10]

# Dónde va la imagen dentro del vertical. 1080×608 es el 16:9 a todo ancho.
IMG_ALTO = 608
IMG_Y = 500

# Los subtítulos. Por debajo de 1550 está la interfaz de YouTube —título,
# canal, botones— así que nada baja de ahí.
SUB_Y = 1300
SUB_TAM = 78
PALABRAS_POR_ROTULO = 3
# Lo ancho que puede ser un rótulo. 1080 menos un margen generoso a cada
# lado: pegado al borde se lee mal y en algunos móviles se recorta.
ANCHO_ROTULO = 930
FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

FONDO = "#0E1014"
CLARO = "#F2F0EB"
AMBAR = "#D69E2E"

SALIDA_X264 = ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-pix_fmt", "yuv420p", "-r", str(FPS)]


def log(m):
    print(f"· {m}", flush=True)


def ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg falló:\n{' '.join(str(a) for a in args)[:400]}\n"
                           f"{r.stderr[-800:]}")


# ───────────────────────────────────────────────────────── los rótulos
def trocear_frase(texto, inicio, duracion):
    """Parte una frase en rótulos de dos o tres palabras, con su segundo.

    El reparto es por caracteres, no por palabras: «a» y «recommendations»
    no se tardan lo mismo en decir, y repartir por palabras hace que el
    subtítulo adelante a la voz en las frases con palabras largas.
    """
    palabras = texto.split()
    grupos, actual = [], []
    for p in palabras:
        actual.append(p)
        # Un rótulo no cruza nunca un punto. En el primer montaje salió
        # «APARTMENTS. KEPT», que junta el final de una frase con el
        # principio de la siguiente: se lee como un trabalenguas y deshace
        # la pausa que la voz sí hace.
        if p.endswith((".", "!", "?", ":", ";")):
            grupos.append(" ".join(actual))
            actual = []
            continue
        # Y se corta por número de palabras, o antes si el rótulo se hace
        # largo. El tope de caracteres no es un gusto: a 86 píxeles y en
        # mayúsculas, «APARTMENTS. KEPT EMPTY.» se salía por los dos lados
        # de la pantalla. Lo que de verdad manda es la medida en píxeles,
        # y de eso se encarga encaje().
        if len(actual) >= PALABRAS_POR_ROTULO or len(" ".join(actual)) >= 16:
            grupos.append(" ".join(actual))
            actual = []
    if actual:
        # Una palabra suelta al final queda huérfana: se pega a la anterior
        # si entre las dos no se pasan.
        cola = " ".join(actual)
        if grupos and len(actual) == 1 and len(grupos[-1]) + len(cola) + 1 <= 18:
            grupos[-1] += " " + cola
        else:
            grupos.append(cola)
    if not grupos:
        return []

    pesos = [max(len(g), 1) for g in grupos]
    total = sum(pesos)
    salida, t = [], inicio
    for g, peso in zip(grupos, pesos):
        d = duracion * peso / total
        salida.append({"texto": g, "inicio": round(t, 3), "duracion": round(d, 3)})
        t += d
    return salida


def ass_color(hexa):
    """#RRGGBB → &H00BBGGRR&, que es como lo quiere ASS."""
    h = hexa.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&"


def ass_tiempo(s):
    h, resto = divmod(max(s, 0), 3600)
    m, seg = divmod(resto, 60)
    return f"{int(h)}:{int(m):02d}:{seg:05.2f}"


def encaje(texto, tam=SUB_TAM, ancho_max=ANCHO_ROTULO):
    """El tamaño más grande al que este rótulo cabe de verdad en pantalla.

    De dónde sale. El primer montaje salió con «APARTMENTS. KEPT EMPTY.»
    cortado por los dos lados: el ASS no envuelve (WrapStyle 2) y 86 píxeles
    en mayúsculas dan para menos de lo que parece. Contar caracteres no
    basta, porque una eme ocupa el triple que una i. Así que se mide con la
    misma fuente que va a usar libass y se baja el cuerpo hasta que entra.
    """
    from PIL import ImageFont
    t = texto.upper()
    for cuerpo in range(tam, 40, -4):
        f = ImageFont.truetype(FUENTE, cuerpo)
        if f.getbbox(t)[2] <= ancho_max:
            return cuerpo
    return 40


def subtitulos(rotulos, destino):
    """Un fichero ASS. libass lo quema en una sola pasada y queda nítido."""
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,DejaVu Sans,{SUB_TAM},{ass_color(CLARO)},{ass_color(CLARO)},&H00000000&,&H00000000&,-1,0,0,0,100,100,0,0,1,7,3,5,80,80,0,1
Style: Cifra,DejaVu Sans,{SUB_TAM},{ass_color(AMBAR)},{ass_color(AMBAR)},&H00000000&,&H00000000&,-1,0,0,0,100,100,0,0,1,7,3,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lineas = []
    for r in rotulos:
        # Un rótulo con cifra o porcentaje va en ámbar: es lo que se viene a
        # ver, y en un Short no hay tiempo de buscarlo.
        estilo = "Cifra" if re.search(r"\d|percent|million|billion|thousand|hundred",
                                      r["texto"], re.I) else "Base"
        texto = r["texto"].replace("\\", "").replace("{", "").replace("}", "")
        fin = r["inicio"] + r["duracion"]
        cuerpo = encaje(texto)
        # \fs por rótulo: el estilo da el cuerpo normal y aquí se baja solo
        # en los que no entran, en vez de encoger todos por culpa del peor.
        tam = "" if cuerpo == SUB_TAM else f"\\fs{cuerpo}"
        lineas.append(f"Dialogue: 0,{ass_tiempo(r['inicio'])},{ass_tiempo(fin)},"
                      f"{estilo},,0,0,0,,{{\\pos({W // 2},{SUB_Y}){tam}}}{texto.upper()}")
    destino.write_text(cab + "\n".join(lineas) + "\n", encoding="utf-8")
    return destino


# ───────────────────────────────────────────────────────── los planos
def repartir(total, imagenes):
    """Cuántos planos y de cuánto, sin salirse de la banda de ritmo."""
    cuantos = max(2, round(total / ((PLANO_MIN + PLANO_MAX) / 2)))
    base = total / cuantos
    duraciones = [base * VAIVEN[i % len(VAIVEN)] for i in range(cuantos)]
    ajuste = total / sum(duraciones)
    return [d * ajuste for d in duraciones]


def elegir(imagenes, cuantos):
    """Una imagen por plano. NUNCA la misma dos veces seguida.

    Es la regla que el montaje largo se saltaba: allí el 33 % del metraje
    eran imágenes repetidas seguidas, hasta 15 segundos en la misma foto.
    Aquí, si hay menos imágenes que planos se da la vuelta a la lista, pero
    jamás se pone una detrás de sí misma.
    """
    if not imagenes:
        raise RuntimeError("Un Short sin imágenes no es un Short.")
    salida = []
    for i in range(cuantos):
        candidata = imagenes[i % len(imagenes)]
        if salida and candidata == salida[-1]:
            candidata = imagenes[(i + 1) % len(imagenes)]
        salida.append(candidata)

    # El bucle: el último plano vuelve al primero y el corte no se nota.
    # Ojo con el caso que se me escapó a la primera: si la penúltima YA era
    # la primera, poner la primera al final deja dos iguales seguidas, que
    # es justo lo que esta función existe para impedir. Entonces se cambia
    # la penúltima por cualquier otra que no choque con sus dos vecinas.
    if len(salida) > 2:
        if salida[-2] == imagenes[0]:
            for alternativa in imagenes:
                if alternativa not in (imagenes[0], salida[-3]):
                    salida[-2] = alternativa
                    break
        if salida[-2] != imagenes[0]:
            salida[-1] = imagenes[0]
    return salida


def plano(ruta, dur, destino, acerca=True):
    """Un plano vertical: la imagen entera sobre su propia copia desenfocada."""
    fot = max(2, int(dur * FPS))
    zoom = (f"1.0+0.07*on/{fot}" if acerca else f"1.07-0.07*on/{fot}")
    filtro = (
        f"[0:v]split=2[bg][fg];"
        # El fondo: la misma imagen, ampliada hasta cubrir, muy desenfocada y
        # oscurecida. No se mira, pero sin él la pantalla tiene dos franjas
        # negras y el Short parece un vídeo mal recortado.
        # Oscurecerlo mucho fue un error: con una imagen ya oscura el fondo
        # salía negro y el Short parecía un vídeo apaisado con bandas. Se
        # deja vivo —solo un punto por debajo— y desaturado, para que se lea
        # como fondo y no compita con la imagen de delante.
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},gblur=sigma=46,eq=brightness=-0.04:saturation=0.45,"
        f"colorlevels=rimin=-0.06:gimin=-0.06:bimin=-0.04[bgb];"
        # La imagen, a todo el ancho, con un empuje lento para que esté viva.
        f"[fg]scale={W * 2}:-1,zoompan=z='{zoom}':d={fot}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{IMG_ALTO}:fps={FPS}[fgz];"
        f"[bgb][fgz]overlay=0:{IMG_Y},format=yuv420p"
    )
    ffmpeg(["-loop", "1", "-i", str(ruta), "-t", f"{dur:.3f}",
            "-filter_complex", filtro, *SALIDA_X264, str(destino)])


# ───────────────────────────────────────────────────────── narración
def narrar(frases, destino_wav):
    """Kokoro, frase a frase, para saber el segundo exacto de cada una."""
    import numpy as np
    import soundfile as sf

    import narrar as n
    pipeline = n.motor()
    pistas, marcas, t = [], [], 0.0
    for texto in frases:
        audio = n.sintetizar(pipeline, texto)
        d = len(audio) / n.FRECUENCIA
        marcas.append({"texto": texto, "inicio": round(t, 3), "duracion": round(d, 3)})
        pistas.append(audio)
        t += d
        # Un respiro corto entre frases: en un Short, una pausa larga es una
        # invitación a deslizar.
        pistas.append(n.silencio(0.12))
        t += 0.12
    audio = np.concatenate(pistas)
    destino_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(destino_wav), audio, n.FRECUENCIA)
    return marcas, round(t, 3)


# ───────────────────────────────────────────────────────── montaje
def montar(corto, marcas, total, wav, destino):
    carpeta = BASE / "videos" / corto["de"] / "imagenes"
    duraciones = repartir(total, corto["imagenes"])
    nombres = elegir(corto["imagenes"], len(duraciones))

    faltan = [n for n in set(nombres) if not (carpeta / f"{n}.jpg").exists()]
    if faltan:
        raise RuntimeError(f"No están estas imágenes en {carpeta}: {', '.join(faltan)}")

    TRABAJO.mkdir(parents=True, exist_ok=True)
    trozos = []
    for i, (nombre, dur) in enumerate(zip(nombres, duraciones)):
        f = TRABAJO / f"{corto['id']}-{i:03d}.mp4"
        plano(carpeta / f"{nombre}.jpg", dur, f, acerca=(i % 2 == 0))
        trozos.append(f)
    log(f"{len(trozos)} planos · {total / len(trozos):.2f}s de media")

    lista = TRABAJO / f"{corto['id']}-lista.txt"
    lista.write_text("".join(f"file '{f.name}'\n" for f in trozos), encoding="utf-8")
    mudo = TRABAJO / f"{corto['id']}-mudo.mp4"
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(mudo)])

    rotulos = []
    for m in marcas:
        rotulos.extend(trocear_frase(m["texto"], m["inicio"], m["duracion"]))
    ass = subtitulos(rotulos, TRABAJO / f"{corto['id']}.ass")
    log(f"{len(rotulos)} rótulos")

    destino.parent.mkdir(parents=True, exist_ok=True)
    # El subtítulo se quema al final, sobre el vídeo ya montado: una sola
    # pasada de libass en vez de uno por trozo.
    ffmpeg(["-i", str(mudo.resolve()), "-i", str(wav.resolve()),
            "-filter_complex", f"[0:v]ass='{ass.as_posix()}'[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:a", "aac", "-b:a", "160k", "-shortest",
            *SALIDA_X264, str(destino)])
    return len(trozos), len(rotulos)


def ficha(corto, total, planos, rotulos, destino):
    """Lo que hace falta para subirlo, en el formato que lee app/subir.py."""
    d = {
        "titulo": corto["titulo"],
        "descripcion": (" ".join(corto["narracion"])[:600]
                        + "\n\n#Shorts " + corto.get("hashtags", "")
                        + "\n\nRounding Error: business stories told through one "
                          "number somebody decided did not matter."
                          "\n\nNarration is synthetic."),
        "etiquetas": [h.lstrip("#") for h in corto.get("hashtags", "").split()],
        "categoria": "25",
        "idioma": "en",
        "para_ninos": False,
        "duracion": total,
        "planos": planos,
        "rotulos": rotulos,
    }
    destino.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False),
                       encoding="utf-8")


def cargar():
    d = yaml.safe_load(DEFINICIONES.read_text(encoding="utf-8"))
    return d.get("cortos", [])


def main():
    cuales = [c.strip() for c in (os.environ.get("CORTO") or "").split(",") if c.strip()]
    todos = cargar()
    lista = [c for c in todos if not cuales or c["id"] in cuales]
    if not lista:
        raise RuntimeError(f"No encuentro {cuales} en {DEFINICIONES.name}. "
                           f"Hay: {', '.join(c['id'] for c in todos)}")

    hechos = []
    for corto in lista:
        log(f"━━ {corto['id']} · {corto['titulo']}")
        wav = TRABAJO / f"{corto['id']}.wav"
        marcas, total = narrar(corto["narracion"], wav)
        log(f"{total:.1f}s de narración")
        if total > 58:
            raise RuntimeError(f"{corto['id']} dura {total:.0f}s y un Short son 60. "
                               "Recorta la narración.")
        if total > 45:
            log(f"OJO: {total:.0f}s. Por encima de 45 cuesta mucho sostener la "
                "atención hasta el final.")
        destino = SALIDA / f"{corto['id']}.mp4"
        planos, rotulos = montar(corto, marcas, total, wav, destino)
        ficha(corto, total, planos, rotulos, SALIDA / f"{corto['id']}.yml")
        log(f"LISTO · {destino.relative_to(BASE)} · {destino.stat().st_size / 1e6:.1f} MB")
        hechos.append({"id": corto["id"], "duracion": total, "planos": planos,
                       "rotulos": rotulos, "archivo": destino.name})

    (SALIDA / "hechos.json").write_text(
        json.dumps(hechos, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"\n{len(hechos)} Shorts montados")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        import traceback
        from datetime import datetime, timezone
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "estado").mkdir(parents=True, exist_ok=True)
        (BASE / "estado" / "ULTIMO-FALLO-CORTO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · corto\n\n{detalle}\n",
            encoding="utf-8")
        raise
