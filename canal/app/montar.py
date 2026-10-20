"""Monta el vídeo: reparte tarjetas, documentos y archivo sobre la narración.

Lee marcas.json (lo que dura cada frase) y montaje.yml (qué se ve en cada
acto), y arma un .mp4 con ffmpeg.

  video/primer-corte.mp4
  video/planos.txt         la lista de planos, para saber qué cambiar

Las reglas que hacen que no canse de ver:

  1. En pantalla tiene que pasar algo. Más o menos un tercio de los planos
     son información escrita — la cifra, la frase, el documento — y no una
     imagen de archivo cualquiera. Ese es el cambio que más se nota.
  2. Los planos no duran todos lo mismo. Cada acto tiene su ritmo y dentro
     del párrafo se alternan planos cortos y largos, para que no suene a
     metrónomo.
  3. Un clip no vuelve hasta pasados 8 planos, y cuando vuelve lo hace con
     otro encuadre, en espejo o empezando por otro punto.
  4. Nunca hay pantalla en negro. Si falta material, se tira de la bolsa.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

import config
import ritmo

BASE = Path(__file__).resolve().parent.parent
AUDIO = BASE / "audio"
MATERIAL = BASE / "material"
GRAFICOS = BASE / "graficos"
ROTULOS = BASE / "rotulos"
MUSICA = BASE / "musica" / "lecho.wav"
FONDO = BASE / "musica" / "fondo.wav"
TRABAJO = BASE / "video" / "trozos"
SALIDA = BASE / "video" / "primer-corte.mp4"

W, H, FPS = 1920, 1080, 30
NEGRO = "#0E1014"
RITMO = 4.3                 # segundos por plano, si el acto no dice otra cosa
PLANO_MIN = 2.2
ANCLA_MAX = 5.4             # lo que aguanta una tarjeta de texto
DISTANCIA = 8               # planos antes de repetir un clip
# Para que el corte no suene a metrónomo: los planos de un mismo párrafo se
# alternan corto/largo en vez de durar todos igual.
VAIVEN = [0.82, 1.18, 0.94, 1.06]


def log(m):
    print(f"· {m}", flush=True)


def ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:300])


# ------------------------------------------------------------- materiales
def localizar(nombre):
    """Devuelve (ruta, tipo). tipo: tarjeta | video | imagen | grafico | falta."""
    if not nombre:
        return None, "falta"
    n = str(nombre)
    # Las tarjetas se buscan primero y en vídeo: están animadas.
    for carpeta, ext, tipo in ((GRAFICOS, ".mp4", "tarjeta"),
                               (MATERIAL / "clips", ".mp4", "video"),
                               (config.VIDEOS / config.cual() / "imagenes", ".jpg", "imagen"),
                               (GRAFICOS, ".png", "grafico"),
                               (MATERIAL / "documentos", ".png", "imagen")):
        exacto = carpeta / f"{n}{ext}"
        if exacto.exists():
            return exacto, tipo
        posibles = sorted(carpeta.glob(f"{n}*{ext}"))
        if posibles:
            return posibles[0], tipo
    return None, "falta"


def rotulo(nombre):
    if not nombre:
        return None
    r = ROTULOS / f"{nombre}.png"
    return r if r.exists() else None


class Bolsa:
    """Reparte clips sin que se repitan cerca de sí mismos."""

    def __init__(self, nombres):
        self.todos = [n for n in nombres if localizar(n)[0]]
        self.recientes = []

    def siguiente(self):
        if not self.todos:
            return None
        libres = [n for n in self.todos if n not in self.recientes]
        elegido = (libres or self.todos)[0]
        self.todos.remove(elegido)
        self.todos.append(elegido)
        self.recientes = (self.recientes + [elegido])[-DISTANCIA:]
        return elegido


# ----------------------------------------------------------------- planos
ESCALA = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},setsar=1,fps={FPS},format=yuv420p")

VARIANTES = [
    "",
    "hflip",
    "crop=iw*0.75:ih*0.75:iw*0.125:ih*0.125",
    "crop=iw*0.8:ih*0.8:0:0",
    "crop=iw*0.8:ih*0.8:iw*0.2:ih*0.2",
    "hflip,crop=iw*0.8:ih*0.8:iw*0.1:ih*0.1",
]

SALIDA_X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-pix_fmt", "yuv420p"]


def plano_negro(dur, destino):
    ffmpeg(["-f", "lavfi", "-i", f"color=c={NEGRO}:s={W}x{H}:r={FPS}:d={dur:.3f}",
            *SALIDA_X264, str(destino)])


def plano_grafico(ruta, dur, destino):
    # Quieto: lleva texto y hay que poder leerlo entero.
    ffmpeg(["-loop", "1", "-i", str(ruta), "-t", f"{dur:.3f}", "-vf", ESCALA,
            *SALIDA_X264, str(destino)])


def plano_tarjeta(ruta, dur, destino, variante=0):
    """La tarjeta ya viene animada: se recorta y se le da un empuje lentísimo.

    Si hiciera falta más de lo que dura, el último fotograma se clona. Eso era
    todo lo que se hacía antes, y era el problema: la tarjeta se animaba
    durante segundo y medio y después se quedaba congelada cinco. El corte
    llegaba a tiempo, pero entre corte y corte no se movía nada y el vídeo
    parecía un pase de diapositivas.

    Ahora se acerca —o se aleja— un dos por ciento a lo largo del plano. Es
    tan poco que no se ve mirando un fotograma; lo que se nota es que la
    imagen está viva.
    """
    # Ojo con zoompan sobre un vídeo.
    #
    # Con d=N, zoompan saca N fotogramas por CADA fotograma de entrada. Sobre
    # una imagen fija es justo lo que se quiere. Sobre un vídeo, congela: la
    # primera versión de esto dejaba la tarjeta clavada en su fotograma cero,
    # que es el de antes de que el texto entre, así que las tarjetas salían
    # vacías. Comprobado midiendo a qué instante del original se parecía la
    # salida: en el segundo 2 mostraba el segundo 0.
    #
    # Con d=1 sale un fotograma por cada uno de entrada y el zoom avanza con
    # el número de fotograma, que es lo que hace falta.
    acerca = variante % 2 == 0
    fotogramas = max(1, int(dur * FPS))
    z = ("scale=%d:%d,zoompan=z='%s':d=1:s=%dx%d:fps=%d,format=yuv420p" % (
        W * 2, H * 2,
        ("1.0+0.02*on/%d" % fotogramas) if acerca else ("1.02-0.02*on/%d" % fotogramas),
        W, H, FPS))
    ffmpeg(["-i", str(ruta), "-t", f"{dur:.3f}", "-an",
            "-vf", f"tpad=stop_mode=clone:stop_duration={dur:.3f},{z}",
            *SALIDA_X264, str(destino)])


# Cómo se encuadra una imagen cada vez que vuelve a salir.
#
# Una imagen larga se parte en varios planos, y antes los trozos se
# distinguían solo por el sentido del empuje: uno acercándose desde 1.00 y
# otro alejándose desde 1.12. En seis segundos eso mueve la imagen un ocho por
# ciento, y el corte no se ve: en el vídeo 3 había trece pares de planos
# seguidos que parecían el mismo fotograma repetido trece segundos.
#
# Ahora cada vuelta enseña un trozo distinto de la foto. Son planos de verdad
# —un general, un detalle a la izquierda, otro a la derecha— sacados de la
# misma imagen, que es lo que haría un montador con una sola fotografía.
# (porción que se conserva, centro horizontal, centro vertical, se acerca)
ENCUADRES = [
    (1.00, 0.50, 0.50, True),    # general, acercándose despacio
    (0.72, 0.18, 0.42, False),   # detalle a la izquierda, alejándose
    (0.72, 0.84, 0.56, True),    # detalle a la derecha, acercándose
    (0.60, 0.50, 0.38, False),   # primer plano del centro, alejándose
]


def plano_imagen(ruta, dur, destino, variante=0, encima=None):
    porcion, cx, cy, acerca = ENCUADRES[variante % len(ENCUADRES)]
    fotogramas = max(1, int(dur * FPS))
    recorte = ""
    if porcion < 0.999:
        recorte = (f"crop=iw*{porcion}:ih*{porcion}:"
                   f"(iw-iw*{porcion})*{cx}:(ih-ih*{porcion})*{cy},")
    # Un seis por ciento de empuje dentro del encuadre: se nota que la imagen
    # está viva sin que parezca un zoom.
    z = (f"{recorte}scale={W*2}:{H*2},zoompan=z='"
         + (f"1.0+0.06*on/{fotogramas}" if acerca else f"1.06-0.06*on/{fotogramas}")
         + f"':d={fotogramas}:s={W}x{H}:fps={FPS},format=yuv420p")
    if encima:
        ffmpeg(["-loop", "1", "-i", str(ruta), "-i", str(encima),
                "-t", f"{dur:.3f}",
                "-filter_complex", f"[0:v]{z}[v];[v][1:v]overlay=0:0",
                *SALIDA_X264, str(destino)])
    else:
        ffmpeg(["-loop", "1", "-i", str(ruta), "-t", f"{dur:.3f}", "-vf", z,
                *SALIDA_X264, str(destino)])


def plano_video(ruta, dur, destino, variante=0, desde=0.0, encima=None):
    pre = VARIANTES[variante % len(VARIANTES)]
    filtro = f"{pre},{ESCALA}" if pre else ESCALA
    entrada = ["-stream_loop", "-1"]
    if desde > 0:
        entrada += ["-ss", f"{desde:.2f}"]
    entrada += ["-i", str(ruta)]
    if encima:
        ffmpeg([*entrada, "-i", str(encima), "-t", f"{dur:.3f}", "-an",
                "-filter_complex", f"[0:v]{filtro}[v];[v][1:v]overlay=0:0",
                *SALIDA_X264, str(destino)])
    else:
        ffmpeg([*entrada, "-t", f"{dur:.3f}", "-an", "-vf", filtro,
                *SALIDA_X264, str(destino)])


# ------------------------------------------------------------------ troceo
def trocear(dur, ritmo):
    """Parte un párrafo en planos, alternando cortos y largos."""
    if dur <= ritmo * 1.35:
        return [dur]
    n = max(2, round(dur / ritmo))
    while dur / n < PLANO_MIN and n > 2:
        n -= 1
    base = dur / n
    trozos = [base * VAIVEN[i % len(VAIVEN)] for i in range(n)]
    ajuste = dur / sum(trozos)
    return [t * ajuste for t in trozos]


def leer_ancla(valor):
    """Admite 'NOMBRE' o {tarjeta, donde, dura}."""
    if valor is None:
        return None, "inicio", None
    if isinstance(valor, dict):
        return valor.get("tarjeta"), valor.get("donde", "inicio"), valor.get("dura")
    return str(valor), "inicio", None


# -------------------------------------------------------------- el plan
def leer_duraciones():
    f = GRAFICOS / "duraciones.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}




# ------------------------------------------------------------------- main
def main():
    marcas_f = AUDIO / "marcas.json"
    if not marcas_f.exists():
        sys.exit("Falta audio/marcas.json. Lanza antes la narración.")
    marcas = json.loads(marcas_f.read_text(encoding="utf-8"))
    parrafos = marcas["planos"]
    monta = yaml.safe_load(config.ruta("montaje.yml").read_text(encoding="utf-8"))
    # "actos" es del formato antiguo, el de la bolsa de clips por acto. Un
    # vídeo con plan escrito frase a frase no lo lleva, y exigirlo tiraba el
    # montaje entero en el último paso, con todo lo demás ya hecho.
    cfg = monta.get("actos") or {}
    (BASE / "video").mkdir(exist_ok=True)
    (BASE / "video" / "sonido.json").write_text(
        json.dumps(monta.get("sonido", {})), encoding="utf-8")

    if TRABAJO.exists():
        shutil.rmtree(TRABAJO)
    TRABAJO.mkdir(parents=True)

    plan = monta.get("plan")
    rotulos_plan = monta.get("rotulos") or {}
    bolsas = {n: Bolsa(a.get("fondo", [])) for n, a in cfg.items()} if cfg else {}
    duraciones = leer_duraciones()
    _t = yaml.safe_load(config.ruta("tarjetas.yml").read_text(encoding="utf-8")) or {}
    fichas = {t["nombre"]: t for t in _t.get("tarjetas", [])}

    veces = {}
    lista, usados, detalle, ultimo = [], [], [], None
    tarjetas = 0
    reloj = 0.0

    for p in parrafos:
        if plan is not None:
            pedidos = (plan.get(p["acto"]) or {}).get(p["parrafo"]) or []
            pedidos = [x for x in pedidos if localizar(x)[0]]
            dur_total = max(p["duracion"], 0.5)
            pedidos = ritmo.ordenar(pedidos, p.get("texto", ""),
                                    lambda x: ritmo.texto_ficha(fichas.get(x)),
                                    p.get("frases"), p.get("inicio"), dur_total)
            if not pedidos:
                pedidos, trozos = ["negro"], [("negro", dur_total)]
            else:
                minimos = {x: ritmo.minimo_de(x, localizar(x)[1], duraciones)
                           for x in pedidos}
                fracs = {x: ritmo.donde(ritmo.texto_ficha(fichas.get(x)),
                                        p.get("texto", ""), p.get("frases"),
                                        p.get("inicio"), dur_total)
                         for x in pedidos}
                trozos = ritmo.repartir(pedidos, dur_total, minimos, fracs,
                                        lambda x: localizar(x)[1] == "tarjeta")
            etiqueta = (rotulos_plan.get(p["acto"]) or {}).get(p["parrafo"])
            remates = set()
            puesto = False
            for i_trozo, (nombre, dur) in enumerate(trozos):
                n = len(lista) + 1
                destino = TRABAJO / f"{n:04d}.mp4"
                ruta, tipo = localizar(nombre)
                v = veces.get(nombre, 0)
                veces[nombre] = v + 1
                encima = None
                if tipo in ("video", "imagen") and etiqueta and not puesto:
                    encima = rotulo(etiqueta)
                    puesto = encima is not None
                try:
                    if tipo == "tarjeta":
                        plano_tarjeta(ruta, dur, destino, tarjetas); tarjetas += 1
                    elif tipo == "grafico":
                        plano_grafico(ruta, dur, destino); tarjetas += 1
                    elif tipo == "imagen":
                        plano_imagen(ruta, dur, destino, variante=v, encima=encima)
                        tarjetas += 1 if encima else 0
                    elif tipo == "video":
                        plano_video(ruta, dur, destino, variante=v,
                                    desde=min(v * 1.5, 4.0), encima=encima)
                    else:
                        plano_negro(dur, destino)
                except RuntimeError as e:
                    log(f"  ⚠ plano {n} ({nombre}): {e}")
                    plano_negro(dur, destino)
                lista.append(destino)
                detalle.append({"inicio": round(reloj, 3), "duracion": round(dur, 3),
                                "material": nombre,
                                "rotulo": etiqueta if encima else None,
                                "remate": False,
                                "texto": p.get("texto", "")[:110] if i_trozo == 0 else ""})
                reloj += dur
                ultimo = nombre
                usados.append(f"{reloj - dur:7.1f}s  {dur:5.2f}s  {p['acto']}.{p['parrafo']:<2} "
                              f"{nombre}{'  ◀' + etiqueta if encima else ''}")
                if n % 30 == 0:
                    log(f"  {n} planos")
            continue

        acto = cfg.get(p["acto"], {})
        # Ojo con el nombre: "ritmo" es también el módulo que se importa
        # arriba. Llamar así a la variable la convertía en local en TODA la
        # función y rompía las llamadas al módulo de más arriba.
        compas = float(acto.get("ritmo", RITMO))
        bolsa = bolsas.get(p["acto"])
        nombre_ancla, donde, dura = leer_ancla((acto.get("anclas") or {}).get(p["parrafo"]))
        etiqueta = (acto.get("rotulos") or {}).get(p["parrafo"])
        dur_total = max(p["duracion"], 0.5)

        # Si la tarjeta ya está en pantalla desde el párrafo anterior, no se
        # repite: ya ha tenido su momento.
        if nombre_ancla and nombre_ancla == ultimo:
            nombre_ancla = None

        trozos = []
        if nombre_ancla:
            d_ancla = min(dur_total, float(dura) if dura else ANCLA_MAX)
            resto = dur_total - d_ancla
            if resto < PLANO_MIN:
                d_ancla, resto = dur_total, 0.0
            relleno = [(bolsa.siguiente() if bolsa else None, d)
                       for d in (trocear(resto, compas) if resto else [])]
            trozos = ([(nombre_ancla, d_ancla)] + relleno if donde != "final"
                      else relleno + [(nombre_ancla, d_ancla)])
            remates = {len(trozos) - 1} if donde == "final" else set()
        else:
            trozos = [(bolsa.siguiente() if bolsa else None, d)
                      for d in trocear(dur_total, compas)]
            remates = set()

        puesto = False      # el rótulo solo va en el primer clip del párrafo
        for i_trozo, (nombre, dur) in enumerate(trozos):
            n = len(lista) + 1
            destino = TRABAJO / f"{n:04d}.mp4"
            ruta, tipo = localizar(nombre)
            v = veces.get(nombre, 0)
            veces[nombre] = v + 1
            encima = None
            if tipo in ("video", "imagen") and etiqueta and not puesto:
                encima = rotulo(etiqueta)
                puesto = encima is not None
            try:
                if tipo == "tarjeta":
                    plano_tarjeta(ruta, dur, destino, tarjetas)
                    tarjetas += 1
                elif tipo == "grafico":
                    plano_grafico(ruta, dur, destino)
                    tarjetas += 1
                elif tipo == "imagen":
                    plano_imagen(ruta, dur, destino, variante=v, encima=encima)
                    tarjetas += 1 if encima else 0
                elif tipo == "video":
                    plano_video(ruta, dur, destino, variante=v,
                                desde=min(v * 1.5, 4.0), encima=encima)
                    if encima:
                        tarjetas += 1
                else:
                    plano_negro(dur, destino)
            except RuntimeError as e:
                log(f"  ⚠ plano {n} ({nombre}): {e}")
                try:
                    if tipo == "video":
                        plano_video(ruta, dur, destino)
                    elif tipo == "tarjeta":
                        plano_grafico(GRAFICOS / f"{nombre}.png", dur, destino)
                    else:
                        plano_negro(dur, destino)
                except RuntimeError:
                    plano_negro(dur, destino)
            lista.append(destino)
            detalle.append({"inicio": round(reloj, 3), "duracion": round(dur, 3),
                            "material": nombre, "rotulo": etiqueta if encima else None,
                            "remate": i_trozo in remates})
            reloj += dur
            ultimo = nombre
            marca = " ◀" + etiqueta if encima else ""
            usados.append(f"{n:4d}  {dur:5.2f}s  acto {p['acto']}·{p['parrafo']:<2}  "
                          f"{nombre}{marca}")
            if n % 30 == 0:
                log(f"  {n} planos")

    media = marcas["total"] / len(lista)
    log(f"{len(lista)} planos · {marcas['total']/60:.1f} min · "
        f"{media:.1f} s de media · {100*tarjetas//len(lista)}% con información en pantalla")
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    (BASE / "video" / "planos.txt").write_text("\n".join(usados) + "\n", encoding="utf-8")
    (BASE / "video" / "planos.json").write_text(json.dumps(detalle), encoding="utf-8")

    # Los efectos se colocan leyendo este mismo montaje, así que caen al
    # fotograma: subida antes de cada cartel, golpe en cada cifra, roce de
    # papel en cada documento, y la música se aparta en los remates.
    try:
        import sonido
        sonido.main()
    except Exception as e:  # noqa: BLE001
        log(f"  ⚠ sin efectos de sonido: {e}")

    orden = TRABAJO / "orden.txt"
    orden.write_text("".join(f"file '{p.name}'\n" for p in lista), encoding="utf-8")

    log("Uniendo y añadiendo la voz…")
    # Todos los planos salen con los mismos ajustes, así que se pueden pegar
    # sin volver a comprimir.
    comun = ["-f", "concat", "-safe", "0", "-i", str(orden),
             "-i", str(AUDIO / "completo.wav")]
    cierre = ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
              "-movflags", "+faststart", "-shortest", str(SALIDA)]

    pista_fondo = FONDO if FONDO.exists() else (MUSICA if MUSICA.exists() else None)
    if pista_fondo:
        log("Mezclando música y efectos por debajo de la voz…")
        # Dos cosas a la vez para que la voz salga limpia:
        #  · se le vacía al fondo el hueco donde vive la voz (1-3 kHz), que
        #    es mejor que bajar el volumen entero;
        #  · el fondo se agacha solo cuando ella habla y vuelve a subir en
        #    los silencios (sidechaincompress).
        mezcla = (
            "[1:a]asplit=2[voz][llave];"
            "[2:a]highpass=f=32,lowpass=f=9000,"
            "equalizer=f=1400:t=q:w=1.1:g=-5,"
            "equalizer=f=2700:t=q:w=1.2:g=-6,"
            "aecho=0.85:0.8:70|130:0.22|0.13,volume=0.30[fondo];"
            "[fondo][llave]sidechaincompress=threshold=0.015:ratio=9:"
            "attack=20:release=650:makeup=1[bajo];"
            "[voz][bajo]amix=inputs=2:duration=first:dropout_transition=0,"
            "alimiter=limit=0.95[a]"
        )
        ffmpeg([*comun, "-i", str(pista_fondo), "-filter_complex", mezcla,
                "-map", "0:v", "-map", "[a]", *cierre])
    else:
        ffmpeg([*comun, *cierre])
    shutil.rmtree(TRABAJO, ignore_errors=True)
    log(f"Listo: {SALIDA.name} ({SALIDA.stat().st_size / 1024 / 1024:.0f} MB)")


if __name__ == "__main__":
    main()
