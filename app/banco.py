"""Un almacén de fotos de Allie ya revisadas, para no depender de la cuota.

El problema que resuelve. Cada publicación generaba sus fotos en el momento, y
la GPU gratuita de Hugging Face tiene una cuota diaria única por cuenta que
comparten todos los espacios. El día que se agota —y se agota con un reel— no
hay fotos, y lo que estaba programado sale sin revisar o no sale. Pasó hoy.

La idea. Cuando hay cuota se genera de más y se guarda aquí, revisado. Cuando
toca publicar, se cogen fotos del banco en vez de generarlas. Así la cuota
puede fallar un día entero sin que la cuenta lo note.

Reglas que importan:
- Nada entra sin pasar el revisor. El banco no es un cajón de descartes.
- Cada foto se apunta con su escena y su etiqueta (casa, calle, café…), para
  poder pedir «tres de casa que vayan juntas» y no mezclar sitios.
- Una foto usada se marca con la fecha, y no se repite mientras quede alguna
  sin usar. Repetir foto en una cuenta de Instagram se ve enseguida.
- Las fotos de una misma tanda comparten ropa y sitio, así que llevan el
  número de tanda: un carrusel se arma con fotos de la misma.

Ficheros:
  banco/fotos/<tanda>-<n>.jpg
  banco/indice.json
"""
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ajustes  # noqa: E402
import gemini  # noqa: E402
import contexto  # noqa: E402
import reel  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
BANCO = BASE / "banco"
FOTOS = BANCO / "fotos"
INDICE = BANCO / "indice.json"

# Los ajustes se leen aquí, al importar, y no dentro de main(). Así los
# comprueba prueba_vacias.py: la primera versión los leía dentro y el test de
# arranque pasaba tan contento mientras el trabajo de las 04:20 se caía en la
# primera línea de main() por un input vacío.
CUANTAS = ajustes.entero("CUANTAS", 9)
TEMAS = ajustes.lista("TEMAS")
# Por encima de esto el banco no genera nada: ya hay colchón.
TECHO = ajustes.entero("TECHO_BANCO", 24)


def log(m):
    print(f"· {m}", flush=True)


def leer():
    if INDICE.exists():
        try:
            return json.loads(INDICE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            log("El índice no se podía leer; empiezo uno nuevo")
    return {"fotos": []}


def guardar(indice):
    BANCO.mkdir(exist_ok=True)
    indice["actualizado"] = datetime.now(timezone.utc).isoformat()
    INDICE.write_text(json.dumps(indice, ensure_ascii=False, indent=1),
                      encoding="utf-8")


def disponibles(indice, etiqueta=None):
    """Fotos sin usar, cuyo archivo sigue estando."""
    fuera = []
    for f in indice["fotos"]:
        if f.get("usada"):
            continue
        if etiqueta and f.get("etiqueta") != etiqueta:
            continue
        if not (FOTOS / f["archivo"]).exists():
            continue
        fuera.append(f)
    return fuera


def coger(cuantas, etiqueta=None, azar=False):
    """Devuelve rutas de fotos sin usar de una misma tanda, y las marca.

    De una misma tanda porque comparten ropa, sitio y luz: es lo que hace que
    un carrusel parezca un momento y no un collage.

    AZAR. En los montajes de prueba (EN_SECO) las fotos se devuelven al banco,
    así que la tanda más antigua se elige SIEMPRE y dos vídeos seguidos abren
    con la misma cara de Allie —Teresa: «la primera foto es idéntica al primer
    vídeo». Con azar=True se coge una tanda al azar (y fotos al azar dentro),
    para que cada vídeo sea distinto. En publicación real sigue mandando la
    antigüedad, que es lo que hace rotar el banco.
    """
    import random
    indice = leer()
    libres = disponibles(indice, etiqueta)
    if not libres:
        return [], indice

    por_tanda = {}
    for f in libres:
        por_tanda.setdefault(f.get("tanda", "?"), []).append(f)
    # La tanda más antigua que dé el número pedido; si ninguna llega, la que
    # más tenga. Antes la más vieja para que el banco rote y no envejezca.
    enteras = sorted((t for t in por_tanda.values() if len(t) >= cuantas),
                     key=lambda t: t[0].get("creada", ""))
    if azar and enteras:
        elegida = list(random.choice(enteras))
        random.shuffle(elegida)
        elegidas = elegida[:cuantas]
    else:
        elegida = enteras[0] if enteras else max(por_tanda.values(), key=len)
        elegidas = elegida[:cuantas]

    cuando = datetime.now(timezone.utc).isoformat()
    for f in elegidas:
        f["usada"] = cuando
    guardar(indice)
    log(f"Del banco: {len(elegidas)} fotos de la tanda {elegidas[0].get('tanda')}"
        f" · quedan {len(disponibles(indice))} libres")
    return [FOTOS / f["archivo"] for f in elegidas], indice


def devolver(rutas):
    """Desmarca fotos cogidas que al final no se publicaron.

    Sin esto, un fallo de montaje o de subida se come fotos buenas: quedan
    marcadas como usadas sin haber salido nunca.
    """
    nombres = {Path(r).name for r in rutas}
    indice = leer()
    tocadas = 0
    for f in indice["fotos"]:
        if f["archivo"] in nombres and f.get("usada"):
            f["usada"] = None
            tocadas += 1
    if tocadas:
        guardar(indice)
        log(f"Devueltas al banco {tocadas} fotos que no se publicaron")


def etiqueta_de(tema):
    t = (tema or "").lower()
    for clave, palabras in (
            ("casa", ("casa", "sofá", "sofa", "manta", "ventana", "cocina",
                      "cama", "home", "indoor")),
            ("cafe", ("café", "cafe", "terraza", "desayuno", "brunch")),
            ("calle", ("calle", "paseo", "parque", "retiro", "ciudad", "madrid",
                       "mercado", "street")),
            ("viaje", ("viaje", "escapada", "tren", "playa", "montaña", "pueblo")),
    ):
        if any(x in t for x in palabras):
            return clave
    return "varios"


def escenas(p, cuantas, tema, vestuario=None, sitio=None):
    """Escenas de una misma tanda: mismo sitio y misma ropa, distinto plano.

    La ropa y el sitio NO los elige el modelo: se le imponen. El 18 de
    octubre el banco tenía 81 fotos y diecisiete llevaban el mismo jersey
    beige, porque cuando un modelo de lenguaje elige vestuario libremente
    elige siempre lo mismo. Pedirle «variedad» no funciona; darle la prenda
    escrita, sí.
    """
    cuando, _ = contexto.momento()
    ropa = (vestuario or ("", "whatever suits the scene"))[1]
    donde = (sitio or ("", ""))[1]
    prompt = f"""Eres el director de fotografía de {p.get('nombre', 'Allie')}.
Su forma de ser: {p.get('personalidad', '')}

{cuando}

Describe {cuantas} fotos del MISMO momento sobre: "{tema}".
Misma ropa, mismo sitio, misma luz. Lo que cambia es el plano y la pose.

OBLIGATORIO, y no es negociable ni mejorable:
- Lleva puesto EXACTAMENTE esto, en las {cuantas} fotos: {ropa}.
  No lo cambies, no lo adornes, no añadas otra prenda encima.
{"- Está aquí: " + donde + "." if donde else ""}
- La escena tiene que encajar con la época del año que te he dicho arriba.

Devuelve SOLO un JSON: {{"escenas": [{", ".join(['"escena en inglés"'] * cuantas)}]}}

Reglas estrictas, cada una viene de un fallo real:
- SOLO el sitio, la ropa, la pose, la luz y el encuadre. NUNCA describas cómo
  es ella: ni pelo, ni ojos, ni edad, ni «a young woman with…». El generador
  parte de una foto suya y si el texto describe el pelo le hace caso al texto
  y dibuja a otra mujer.
- Empieza cada escena por «The same woman, ».
- Solo medio cuerpo o primer plano. Nada de cuerpo entero: ahí se inventan
  piernas.
- Nunca sujeta nada con las manos. Ni taza, ni móvil, ni libro.
- Boca cerrada o sonrisa suave de labios juntos.
- Sin texto ni logotipos en la imagen. Apto para todos los públicos."""
    g = gemini.json_(prompt)
    fila = (g.get("escenas") or [])[:cuantas]
    while len(fila) < cuantas:
        fila.append(fila[-1] if fila else f"The same woman, {tema}")
    return fila


def _tanda_libre(tanda, indice):
    """Un nombre de tanda que no esté usado ya.

    La tanda no es solo un prefijo: es lo que dice «estas fotos comparten
    ropa, sitio y luz», y coger() arma los carruseles con fotos de una misma.
    Si dos temas distintos acaban compartiendo tanda, el carrusel puede salir
    con la cafetería y la calle mezcladas, que es justo lo que no debe pasar.
    """
    usadas = {f.get("tanda") for f in indice.get("fotos", [])}
    if tanda not in usadas:
        return tanda
    for letra in "bcdefghijklmnopqrstuvwxyz":
        if f"{tanda}{letra}" not in usadas:
            return f"{tanda}{letra}"
    return f"{tanda}-{int(time.time())}"


def _libre(nombre):
    """Un nombre que no pise ninguna foto que ya esté en el banco.

    El cinturón, además del tirante de los segundos: una foto del banco costó
    una llamada y perderla porque dos nombres coincidieron no se arregla
    después, porque no queda ni rastro de que existió.
    """
    if not (FOTOS / nombre).exists():
        return nombre
    raiz, punto, ext = nombre.rpartition(".")
    for letra in "bcdefghijklmnopqrstuvwxyz":
        otro = f"{raiz}{letra}{punto}{ext}"
        if not (FOTOS / otro).exists():
            return otro
    return f"{raiz}-{int(time.time())}{punto}{ext}"


def llenar(cuantas, tema, vestuario=None, sitio=None):
    """Genera hasta `cuantas` fotos nuevas y las mete en el banco.

    Para en cuanto la cuota se agota y guarda lo conseguido: media tanda en el
    banco vale, y perderla por querer la tanda entera no.
    """
    p = reel.persona()
    FOTOS.mkdir(parents=True, exist_ok=True)
    indice = leer()
    # Con SEGUNDOS, no solo minutos. main() llama aquí una vez por tema, y
    # con Cloudflare una foto tarda ocho segundos: dos temas caían dentro del
    # mismo minuto, les tocaba el mismo nombre de tanda y la segunda foto
    # machacaba a la primera en disco, dejando además dos fichas en el índice
    # apuntando al mismo archivo. Con Hugging Face no pasaba porque cada foto
    # tardaba minutos: el fallo solo aparece cuando las cosas van rápido.
    tanda = _tanda_libre(datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
                         indice)
    etiqueta = etiqueta_de(tema)
    log(f"Tanda {tanda} · {tema} · etiqueta «{etiqueta}»")

    fila = escenas(p, cuantas, tema, vestuario, sitio)
    metidas, motivos = 0, []
    for i, escena in enumerate(fila, 1):
        for intento in range(reel.INTENTOS):
            try:
                datos, fallos = reel.kontext(escena, p)
            except reel.SinCuota as e:
                motivos.append(f"cortado por cuota en la foto {i}: {e}")
                log(f"Se agotó la cuota en la foto {i}; guardo lo que haya")
                guardar(indice)
                return metidas, motivos
            if datos is None:
                motivos.append(f"foto {i} intento {intento + 1}: "
                               + " | ".join(fallos or ["sin motivo"]))
                time.sleep(reel.ESPERAS[min(intento, len(reel.ESPERAS) - 1)])
                continue
            ok, problema = gemini.revisar_imagen(datos, reel.referencia_bytes(p))
            if not ok:
                motivos.append(f"foto {i} intento {intento + 1}: {problema}")
                log(f"Foto {i} descartada ({problema})")
                if intento == 1:
                    escena = reel.sin_manos(escena)
                time.sleep(2)
                continue
            nombre = _libre(f"{tanda}-{i}.jpg")
            (FOTOS / nombre).write_bytes(datos)
            indice["fotos"].append({
                "archivo": nombre, "tanda": tanda, "etiqueta": etiqueta,
                "tema": tema, "escena": escena, "usada": None,
                "vestuario": (vestuario or ("", ""))[0],
                "sitio": (sitio or ("", ""))[0],
                "creada": datetime.now(timezone.utc).isoformat(),
            })
            metidas += 1
            log(f"Foto {i} al banco ({nombre})")
            guardar(indice)   # en cada una: si revienta, lo ganado se queda
            break
    return metidas, motivos


def main():
    cuantas, pedidos = CUANTAS, TEMAS
    p = reel.persona()
    temas = list(pedidos)
    if not temas:
        disponibles_temas = p.get("temas_reel") or ["una tarde tranquila en casa"]
        # Un tema por cada tres fotos, y nunca más temas que eso.
        #
        # Antes eran siempre tres temas. Para llenar el banco con variedad
        # está bien, pero el reel pide CUATRO fotos y le salían repartidas
        # entre tres temas: una de cada, tres tandas distintas, y ninguna
        # tanda con las cuatro que el reel necesita. El trabajo generaba las
        # fotos, pagaba por ellas y luego fallaba al montar.
        #
        # Las fotos de un reel tienen que compartir ropa, sitio y luz, o el
        # vídeo parece cuatro días distintos pegados.
        temas = random.sample(disponibles_temas,
                              min(max(1, cuantas // 3), len(disponibles_temas)))
    por_tema = max(1, cuantas // len(temas))

    indice = leer()
    libres = disponibles(indice)
    log(f"El banco tiene {len(libres)} fotos libres de "
        f"{len(indice['fotos'])} en total")

    # Con el banco lleno, no se genera. El 16 de octubre había 71 fotos
    # libres y aun así se intentó generar más, se agotó la cuota de Gemini a
    # media mañana y el reel del día no salió: la cuenta se quedó muda
    # teniendo material de sobra para tres semanas. Generar es para tener
    # colchón, no para gastarlo porque sí.
    if len(libres) >= TECHO:
        log(f"No genero: con {len(libres)} libres (techo {TECHO}) hay de sobra.")
        guardar(indice)
        return

    # La ropa y el sitio se deciden AQUÍ y no los elige el modelo, que
    # elegiría beige otra vez. Se mira lo usado en las últimas tandas para
    # no repetir: con treinta prendas y azar puro, la misma sale dos veces
    # por semana y el perfil parece el mismo día en bucle.
    _, letra = contexto.momento()
    usados_v, usados_s = contexto.ultimos(indice)
    log(f"Temporada «{letra}» · evito lo último: {', '.join(usados_v[:4]) or '—'}")

    total, motivos = 0, []
    for tema in temas:
        vestuario, sitio = contexto.elegir(letra, usados_v, usados_s)
        usados_v = [vestuario[0]] + usados_v
        usados_s = [sitio[0]] + usados_s
        log(f"  {tema} → {vestuario[0]} · {sitio[0]}")
        n, m = llenar(por_tema, tema, vestuario, sitio)
        total += n
        motivos += m
        if any("cuota" in x for x in m):
            log("Sin cuota: no sigo con los demás temas")
            break

    indice = leer()
    (BANCO / "ultimo-llenado.json").write_text(json.dumps({
        "cuando": datetime.now(timezone.utc).isoformat(),
        "temas": temas, "metidas": total, "motivos": motivos,
        "libres": len(disponibles(indice)), "total": len(indice["fotos"]),
        # En qué se fue la cuota. Se mide en segundos de GPU, no en imágenes:
        # cinco minutos al día en la cuenta gratuita, así que saber cuántos
        # segundos cuesta cada foto es saber cuántas fotos caben.
        "gasto": reel.GASTO,
        "segundos_total": round(sum(g["segundos"] for g in reel.GASTO), 1),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"\n{total} fotos nuevas · el banco queda con "
        f"{len(disponibles(indice))} libres")
    if total == 0:
        raise RuntimeError(
            "No entró ninguna foto al banco. Los motivos están en "
            "banco/ultimo-llenado.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(detalle, flush=True)
        (BASE / "ULTIMO-FALLO.txt").write_text(
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · banco\n\n"
            f"{detalle}\n", encoding="utf-8")
        sys.exit(1)
