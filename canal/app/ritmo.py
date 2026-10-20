"""Coloca cada cosa en el momento del párrafo en que se dice.

El fallo era este. El plan decía, para cada párrafo, qué se ve; el programa lo
servía por orden de lista. Así que si un párrafo de diecinueve segundos decía
la cifra a los catorce, pero la tarjeta con la cifra era la segunda de la
lista, la tarjeta salía a los cuatro: el número aparecía en pantalla diez
segundos antes de que la voz lo dijera, y cuando lo decía ya no estaba.

Aquí se busca, dentro del texto del párrafo, dónde se dice lo que pone cada
tarjeta —incluidos los números, que el guion escribe con letra («a hundred and
fifteen percent») y la tarjeta con cifra («+115%»)— y se ordena por ahí. Lo que
no tiene nada que buscar (una imagen, un clip) se queda donde estaba.
"""
import re

CAPITULO = 2.4          # lo que dura una tarjeta de capítulo: es un rótulo, no una idea

UNIDADES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
            "sixteen", "seventeen", "eighteen", "nineteen"]
DECENAS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty",
           7: "seventy", 8: "eighty", 9: "ninety"}


def en_letra(n):
    """115 → ['a hundred and fifteen', 'one hundred and fifteen', 'hundred and fifteen']."""
    if n < 20:
        return [UNIDADES[n]]
    if n < 100:
        d, u = divmod(n, 10)
        return [DECENAS[d] + (f" {UNIDADES[u]}" if u else "")]
    c, r = divmod(n, 100)
    cola = (" and " + en_letra(r)[0]) if r else ""
    cien = UNIDADES[c] + " hundred"
    salida = [cien + cola, "hundred" + cola]
    if c == 1:
        salida.insert(0, "a hundred" + cola)
    return salida


def limpio(t):
    """El guion escribe «twenty-four»; la búsqueda no debe tropezar con el guion."""
    return re.sub(r"[^a-z0-9 ]+", " ", (t or "").lower()).replace("  ", " ")


def anclas(texto_tarjeta):
    """Qué palabras de la tarjeta se pueden buscar en el párrafo."""
    bruto = texto_tarjeta or ""
    salida = []
    for n in {int(x) for x in re.findall(r"\d+", bruto) if int(x) < 1000}:
        salida.extend(en_letra(n))
        salida.append(str(n))
    # Nombres propios y palabras largas: lo distintivo de la tarjeta.
    for w in re.findall(r"[A-Za-z][a-z]{4,}", bruto):
        salida.append(w.lower())
    return salida


def donde(texto_tarjeta, parrafo, frases=None, inicio=None, duracion=None):
    """Fracción del párrafo (0–1) en la que se dice esto. None si no se dice.

    Con las frases medidas —que es lo que da la narración desde que se genera
    frase a frase— el sitio es exacto: se busca en qué frase se dice y se
    devuelve el segundo en que esa frase empieza. Sin ellas se cae en la
    estimación de antes, contar caracteres, que supone que se habla a ritmo
    constante y no tiene en cuenta las pausas de los puntos.
    """
    if frases and duracion:
        for f in frases:
            hilo = limpio(f.get("texto", ""))
            if not hilo:
                continue
            if any(limpio(a).strip() and limpio(a).strip() in hilo
                   for a in anclas(texto_tarjeta)):
                return min(max((f["inicio"] - (inicio or 0)) / duracion, 0.0), 1.0)

    hilo = limpio(parrafo)
    if not hilo:
        return None
    mejor = None
    for a in anclas(texto_tarjeta):
        i = hilo.find(limpio(a).strip())
        if i >= 0 and (mejor is None or i < mejor):
            mejor = i
    return None if mejor is None else mejor / max(len(hilo), 1)


def ordenar(items, parrafo, texto_de, frases=None, inicio=None, duracion=None):
    """Ordena lo que se ve según cuándo se dice.

    Las tarjetas de capítulo van siempre delante: son el letrero del acto, no
    una idea del párrafo. Lo que no se puede buscar conserva su sitio: se le da
    la posición que le tocaba por orden de lista, así que si yo lo puse tercero
    sigue cayendo por el tercio final del párrafo.
    """
    if len(items) < 2:
        return list(items)
    cabeza = [x for x in items if str(x).startswith("C") and str(x)[1:].isdigit()]
    resto = [x for x in items if x not in cabeza]
    n = max(len(resto) - 1, 1)
    claves = []
    for i, x in enumerate(resto):
        f = donde(texto_de(x), parrafo, frases, inicio, duracion)
        claves.append((f if f is not None else i / n, i, x))
    claves.sort(key=lambda c: (c[0], c[1]))
    return cabeza + [c[2] for c in claves]


def texto_ficha(f):
    """Lo que pone la tarjeta, sea del formato que sea."""
    if not f:
        return ""
    if f.get("filas"):
        return " ".join(f"{x['de']} {x['a']}" for x in f["filas"])
    t = f.get("lineas") or f.get("texto") or f.get("numero") or f.get("titulo") or ""
    if isinstance(t, list):
        t = " ".join(str(x) for x in t)
    return f"{t} {f.get('pie', '')}".strip()


ADELANTO = 0.8          # la tarjeta entra un poco antes de que la voz lo diga
TECHO_IMAGEN = 7.5      # máximo que una imagen se queda sin reencuadrar
TECHO_TARJETA = 6.5     # y una tarjeta, que cansa antes que una foto


def repartir(items, total, minimos, fracciones=None, es_tarjeta=None):
    """Reparte el tiempo del párrafo poniendo cada cosa en su momento.

    Lo que tiene un sitio en el guion —una tarjeta con una cifra que la voz
    dice a los catorce segundos— se clava ahí, entrando un pelo antes para que
    se lea mientras se oye. Lo que no tiene sitio (una imagen, un clip) se mete
    en el hueco más holgado que quede. Si no cabe todo, cae lo último: más vale
    enseñar dos cosas bien que cuatro a medias.
    """
    fracciones = fracciones or {}
    es_tarjeta = es_tarjeta or (lambda x: False)
    vivos = list(items)
    while len(vivos) > 1 and sum(minimos[x] for x in vivos) > total:
        sueltos = [x for x in vivos if fracciones.get(x) is None]
        vivos.remove(sueltos[-1] if sueltos else vivos[-1])

    fijos = [x for x in vivos if fracciones.get(x) is not None]
    libres = [x for x in vivos if fracciones.get(x) is None]
    if not fijos:
        orden = libres
    else:
        # Cada fijo quiere empezar donde se dice; se respeta el mínimo del anterior.
        quiere = {x: max(0.0, fracciones[x] * total - ADELANTO) for x in fijos}
        orden = list(fijos)
        for x in libres:
            # al hueco con más holgura, y si no hay, al final
            huecos = []
            for i in range(len(orden) + 1):
                antes = quiere.get(orden[i - 1], 0.0) + minimos[orden[i - 1]] if i else 0.0
                despues = quiere.get(orden[i], total) if i < len(orden) else total
                huecos.append((despues - antes, i))
            holgura, donde_va = max(huecos)
            orden.insert(donde_va if holgura >= minimos[x] else len(orden), x)

    # Pasada hacia delante: nadie empieza antes de que acabe el anterior.
    inicios, t = [], 0.0
    for x in orden:
        t = max(t, quiere.get(x, t) if fijos else t)
        inicios.append(t)
        t += minimos[x]
    if t > total:                            # se ha ido de tiempo: se aprieta
        inicios = [i * (total - minimos[orden[-1]]) / max(inicios[-1], 0.01)
                   if inicios[-1] > 0 else 0.0 for i in inicios]

    # Pasada hacia atrás: si a algo le falta tiempo, se adelanta su entrada
    # hasta donde el anterior lo permita. Una tarjeta que no se puede leer no
    # sirve de nada, y casi siempre hay hueco justo antes.
    for i in range(len(orden) - 1, -1, -1):
        fin = inicios[i + 1] if i + 1 < len(orden) else total
        falta = minimos[orden[i]] - (fin - inicios[i])
        if falta > 0.01:
            tope = inicios[i - 1] + minimos[orden[i - 1]] if i else 0.0
            inicios[i] = max(tope, inicios[i] - falta)

    duras = []
    for i, x in enumerate(orden):
        fin = inicios[i + 1] if i + 1 < len(orden) else total
        duras.append((x, max(fin - inicios[i], 0.3)))
    # Nada puede durar más que su párrafo: si se sale, el vídeo entero se
    # desplaza y la voz deja de ir con lo que se ve. Se recorta a lo que hay.
    exceso = sum(d for _, d in duras) - total
    if exceso > 0.01:
        factor = total / (total + exceso)
        duras = [(x, d * factor) for x, d in duras]

    sobra = total - sum(d for _, d in duras)
    if sobra > 0.05:                         # lo que sobra, a las imágenes
        estirables = [i for i, (x, _) in enumerate(duras) if not es_tarjeta(x)] \
            or list(range(len(duras)))
        for i in estirables:
            duras[i] = (duras[i][0], duras[i][1] + sobra / len(estirables))

    # Ninguna tarjeta se queda parada el triple de lo que cuesta leerla.
    #
    # Lo último de un párrafo se come todo el tiempo que sobra, porque dura
    # hasta que el párrafo acaba. Si lo último es una tarjeta de dos líneas,
    # salen trece segundos de pantalla quieta —pasó, y se nota mucho—. Se le
    # pone techo y lo que sobre se reparte: primero a las imágenes, que
    # aguantan el movimiento, y si no hay ninguna, entre todas por igual, que
    # es peor pero nunca deja una sola clavada.
    TECHO = 1.45
    sobrante = 0.0
    topados = set()
    for i, (x, d) in enumerate(duras):
        if not es_tarjeta(x):
            continue
        tope = max(minimos.get(x, d) * TECHO, 4.0)
        if d > tope + 0.05:
            sobrante += d - tope
            duras[i] = (x, tope)
            topados.add(i)
    # Al que se le acaba de quitar tiempo no se le devuelve. Y si no hay
    # nadie más a quien dárselo, el recorte se deshace entero.
    #
    # La versión anterior acababa en `or list(range(len(duras)))`, que incluye
    # a la propia tarjeta topada: en un párrafo cuyo único elemento es una
    # tarjeta, se le quitaba el sobrante y se le devolvía en la misma línea.
    # El techo no servía de nada y ocho tarjetas del vídeo 3 quedaron entre
    # ocho y diecisiete segundos congeladas. Devolverlo a propósito, y no por
    # accidente, deja el párrafo sin agujero negro; de que una tarjeta sola no
    # dure diecisiete segundos se encarga el reparto de material, y de avisar,
    # la comprobación del plan.
    reciben = [i for i, (x, _) in enumerate(duras) if not es_tarjeta(x)] \
        or [i for i in range(len(duras)) if i not in topados]
    if sobrante > 0.05 and reciben:
        for i in reciben:
            duras[i] = (duras[i][0], duras[i][1] + sobrante / len(reciben))
    elif sobrante > 0.05:
        for i in topados:
            duras[i] = (duras[i][0], duras[i][1] + sobrante / len(topados))

    # Antes de nada, repartir el tiempo entre las imágenes a partes iguales.
    #
    # Lo último de un párrafo se queda con todo lo que sobra, así que en un
    # párrafo de treinta segundos salían dos imágenes de dos segundos y medio
    # y una de diecinueve. Teniendo tres cosas que enseñar, enseñarlas el
    # mismo rato es mejor que enseñar dos de refilón y una eterna.
    sueltas = [i for i, (x, _) in enumerate(duras) if not es_tarjeta(x)]
    if len(sueltas) > 1:
        reparto = sum(duras[i][1] for i in sueltas) / len(sueltas)
        for i in sueltas:
            duras[i] = (duras[i][0], reparto)

    # Y ninguna imagen se queda diecisiete segundos en pantalla.
    #
    # Al poner techo a las tarjetas, todo el tiempo sobrante se fue a las
    # imágenes: una llegó a durar 17,5 segundos. Una imagen con un empuje
    # lentísimo aguanta mejor que una tarjeta, pero no tanto. Lo que se hace
    # no es recortarla —el párrafo dura lo que dura— sino partirla en varios
    # planos de la misma cosa, que el montaje encuadra distinto cada vez. Se
    # ve la misma imagen y aun así la pantalla cambia.
    # Las tarjetas que no se han podido topar se parten igual. Una tarjeta de
    # trece segundos es un error de reparto de material y hay que arreglarlo
    # ahí, pero mientras tanto más vale que la pantalla se mueva: el montaje
    # da a cada trozo un empuje distinto, uno acercándose y otro alejándose.
    partidas = []
    for x, d in duras:
        techo = TECHO_TARJETA if es_tarjeta(x) else TECHO_IMAGEN
        if d <= techo + 0.4:
            partidas.append((x, d))
            continue
        trozos = int(d // techo) + 1
        partidas.extend([(x, d / trozos)] * trozos)

    # Y partida no quiere decir repetida dos veces seguidas. Si en una tirada
    # hay tres imágenes y cada una va dos veces, se alternan —a, b, c, a, b,
    # c— en vez de ir en parejas. Es la misma pantalla cambiando el doble.
    salida, i = [], 0
    while i < len(partidas):
        j = i
        while j < len(partidas) and not es_tarjeta(partidas[j][0]):
            j += 1
        if j - i > 1:
            porNombre = {}
            for pieza in partidas[i:j]:
                porNombre.setdefault(pieza[0], []).append(pieza)
            colas = list(porNombre.values())
            while any(colas):
                for c in colas:
                    if c:
                        salida.append(c.pop(0))
        else:
            salida.extend(partidas[i:j])
        if j < len(partidas):
            salida.append(partidas[j])
        i = j + 1
    return salida


def minimo_de(nombre, tipo, duraciones, suelo_imagen=2.4):
    """Cuánto tiempo necesita como mínimo esta cosa en pantalla."""
    if str(nombre).startswith("C") and str(nombre)[1:].isdigit():
        return CAPITULO
    if tipo == "tarjeta":
        return duraciones.get(nombre, 5.0)
    return suelo_imagen
