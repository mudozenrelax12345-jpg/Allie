"""Hablar con cualquier espacio de Hugging Face que edite una imagen.

Por qué existe. El código original hablaba un solo dialecto, el de
FLUX.1-Kontext-Dev: llamaba a `/infer` con los parámetros `input_image` y
`prompt`, que son los suyos. Eso ató el proyecto a un modelo concreto, y
resultó que ese modelo tiene dos problemas: su licencia prohíbe el uso
comercial, y a 28 pasos cada foto se come un minuto largo de los cinco que
da la cuota gratuita al día.

Cambiar de modelo era imposible sin esto, porque cada espacio llama a sus
parámetros como quiere. Aquí se le pregunta al espacio cómo se llaman los
suyos y se rellenan todos, que es lo que ya hacía el rastreador: esa lógica
vivía allí y ahora vive aquí, para que la usen los dos.

Y se mide el tiempo de cada llamada, porque la cuota de Hugging Face no se
cuenta en imágenes sino en segundos de GPU. Sin medirlo, no hay forma de
saber si un modelo cabe o no en el día.
"""
import re
import time

PASOS = 8          # pasos de cálculo por omisión: menos pasos, menos cuota
ANCHO = 1024
ALTO = 1280


def apis_de(cli, probables=("/infer", "/edit_image", "/generate", "/process",
                            "/run", "/predict")):
    """Los nombres de API que el espacio dice tener, en vez de adivinarlos.

    Los que suenan a generar van primero; los que suenan a cargar ejemplos o
    a mover la interfaz, al final, porque no generan nada.
    """
    try:
        info = cli.view_api(return_format="dict", print_info=False) or {}
    except Exception:  # noqa: BLE001
        return list(probables)
    nombres = list((info.get("named_endpoints") or {}).keys())
    if not nombres:
        return list(probables)

    def peso(n):
        if re.search(r"example|load|change|select|clear|reset|random|lambda|ui",
                     n, re.I):
            return 2
        if re.search(r"infer|edit|generate|run|process|predict|submit", n, re.I):
            return 0
        return 1
    nombres.sort(key=peso)
    return nombres


def firma(cli, nombre):
    """Los parámetros de esa API con todo lo que se sabe de cada uno."""
    try:
        info = cli.view_api(return_format="dict", print_info=False) or {}
    except Exception:  # noqa: BLE001
        return None
    for sitio in ("named_endpoints", "unnamed_endpoints"):
        ep = (info.get(sitio) or {}).get(nombre)
        if ep:
            return [{
                "nombre": p.get("parameter_name") or p.get("label") or "",
                "etiqueta": p.get("label") or "",
                "componente": p.get("component") or "",
                "obligatorio": not p.get("parameter_has_default", False),
                "defecto": p.get("parameter_default"),
                "tipo": (p.get("python_type") or {}).get("type", ""),
            } for p in (ep.get("parameters") or [])]
    return None


def _es(campo, patron):
    return bool(re.search(patron, str(campo.get("nombre", "")) + " "
                          + str(campo.get("etiqueta", "")), re.I))


def relleno(campo, ref, handle_file, pasos=PASOS):
    """Qué mandar en un campo que no es la imagen ni el texto.

    Los pasos de cálculo se fuerzan SIEMPRE, tenga o no valor por omisión:
    son lo que decide cuánta cuota gasta la llamada, y los espacios suelen
    venir con 28 o 50 de fábrica.
    """
    if _es(campo, r"steps|num_inference"):
        return pasos, True
    if not campo["obligatorio"]:
        return None, False
    if campo["defecto"] is not None:
        return campo["defecto"], True
    comp = str(campo["componente"]).lower()
    if comp in ("image", "imageeditor") or _es(campo, r"image|img|photo"):
        return handle_file(str(ref)), True
    # Algunos espacios declaran el componente como «Api» y no dicen más, así
    # que estos se reconocen por el nombre: son los ajustes de siempre.
    if _es(campo, r"seed"):
        return 0, True
    if _es(campo, r"guidance"):
        return 2.5, True
    if _es(campo, r"strength|denois"):
        return 0.8, True
    if _es(campo, r"width"):
        return ANCHO, True
    if _es(campo, r"height"):
        return ALTO, True
    if _es(campo, r"randomize|random_seed"):
        return True, True
    if comp in ("slider", "number"):
        return 1, True
    if comp == "checkbox":
        return False, True
    if comp in ("dropdown", "radio"):
        return None, False   # sin saber las opciones, mejor no inventar
    if comp in ("textbox", "text"):
        return "", True
    return None, False


def imagen_de(resultado):
    """Gradio devuelve una ruta, una lista o un diccionario, según el espacio."""
    from pathlib import Path
    pendientes = [resultado]
    while pendientes:
        x = pendientes.pop(0)
        if isinstance(x, (list, tuple)):
            pendientes.extend(x)
        elif isinstance(x, dict):
            pendientes.extend(x.values())
        elif isinstance(x, str) and Path(x).exists() and \
                Path(x).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            return x
    return None


def entrar(espacio, ficha):
    """Abre el espacio. Con cuenta si hay ficha; el nombre del parámetro
    cambia según la versión de la librería, así que se prueban los tres."""
    from gradio_client import Client
    if ficha:
        for como in ("hf_token", "auth_token", "token"):
            try:
                return Client(espacio, verbose=False, **{como: ficha})
            except TypeError:
                continue
    return Client(espacio, verbose=False)


def generar(espacio, ficha, referencia, orden, pasos=PASOS):
    """(ruta_de_la_imagen, segundos, api) o (None, 0, motivos).

    `referencia` es la ruta de la foto de partida. `orden` es el texto.
    """
    from gradio_client import handle_file
    cli = entrar(espacio, ficha)
    quejas = []
    for api in apis_de(cli)[:8]:
        campos = firma(cli, api)
        if campos is None:
            continue
        # La imagen se busca primero por componente, que es lo que de verdad
        # lo dice, y solo después por el nombre.
        img = next((c for c in campos
                    if str(c["componente"]).lower() in ("image", "imageeditor")), None) \
            or next((c for c in campos if _es(c, r"image|img|photo|picture")), None)
        txt = next((c for c in campos if _es(c, r"prompt|instruction|caption|edit")), None) \
            or next((c for c in campos
                     if str(c["componente"]).lower() in ("textbox", "text")), None)
        if not img or not txt:
            quejas.append(f"{api}: no encuentro imagen+texto")
            continue

        argumentos = {img["nombre"]: handle_file(str(referencia)),
                      txt["nombre"]: orden}
        faltan = []
        for c in campos:
            if c["nombre"] in argumentos:
                continue
            valor, sirve = relleno(c, referencia, handle_file, pasos)
            if sirve:
                argumentos[c["nombre"]] = valor
            elif c["obligatorio"]:
                faltan.append(f"{c['nombre']}({c['componente']})")
        if faltan:
            quejas.append(f"{api}: no sé qué poner en {', '.join(faltan)}")
            continue

        t0 = time.time()
        try:
            salida = cli.predict(api_name=api, **argumentos)
        except Exception as e:  # noqa: BLE001
            quejas.append(f"{api}: {type(e).__name__}: {str(e)[:200]}")
            continue
        ruta = imagen_de(salida)
        if not ruta:
            quejas.append(f"{api}: contestó sin imagen")
            continue
        return ruta, round(time.time() - t0, 1), api
    return None, 0, quejas
