"""Leer ajustes del entorno sin que un valor vacío tumbe el trabajo.

Viene de un fallo real. Los workflows pasan los inputs de workflow_dispatch
como variables de entorno, y en una ejecución programada esos inputs no
existen: GitHub no deja la variable sin poner, la pone en cadena vacía. Así
que `int(os.environ.get("CUANTAS", "9"))` recibe "" —no el valor por omisión,
porque la variable sí está— y revienta. El banco de fotos de Allie se cayó la
primera noche por esto, a las 04:20, con la cuota recién renovada y nadie
mirando.

El valor por omisión tiene que aplicarse también cuando el valor está pero
está vacío.
"""
import os


def texto(nombre, defecto=""):
    v = os.environ.get(nombre)
    return defecto if v is None or not str(v).strip() else str(v).strip()


def entero(nombre, defecto):
    v = texto(nombre)
    if not v:
        return defecto
    try:
        return int(float(v))
    except ValueError:
        print(f"· {nombre}={v!r} no es un número; uso {defecto}", flush=True)
        return defecto


def lista(nombre, separador="|"):
    return [x.strip() for x in texto(nombre).split(separador) if x.strip()]
