"""Comprobaciones de diez segundos que ahorran cuarenta minutos.

El montaje es el último paso de un trabajo largo: narración, material,
imágenes, tarjetas y música van antes. Un error tonto en montar.py no se ve
hasta que todo lo demás está hecho y se ha gastado la media hora. Estas
comprobaciones se hacen al principio, sin ejecutar nada.

De momento busca lo que ya ha pasado: una variable local que tape el nombre de
un módulo importado. Python entonces trata ese nombre como local en TODA la
función, y las llamadas al módulo que estaban más arriba fallan con un
UnboundLocalError que no señala a la línea culpable.
"""
import ast
import pathlib
import sys

CARPETA = pathlib.Path(__file__).resolve().parent


def tapados(fichero):
    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    modulos = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            modulos |= {(a.asname or a.name.split(".")[0]) for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            modulos |= {(a.asname or a.name) for a in n.names}

    fallos = []
    for fn in ast.walk(arbol):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        asignados = {n.id for n in ast.walk(fn)
                     if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        globales = {g for d in ast.walk(fn) if isinstance(d, ast.Global) for g in d.names}
        usados_como_modulo = {a.value.id for a in ast.walk(fn)
                              if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name)}
        grave = (asignados & modulos & usados_como_modulo) - globales
        for nombre in sorted(grave):
            fallos.append(f"{fichero.name}:{fn.lineno} · {fn.name}() usa «{nombre}» "
                          f"como variable y como módulo a la vez")
    return fallos


def main():
    fallos = []
    for f in sorted(CARPETA.glob("*.py")):
        if f.name == "revisar.py":
            continue
        try:
            fallos += tapados(f)
        except SyntaxError as e:
            fallos.append(f"{f.name}: no se puede ni leer · {e}")
    if fallos:
        print("✗ Revisión previa:")
        for x in fallos:
            print("  ·", x)
        sys.exit(1)
    print("✓ Revisión previa: nada que objetar")


if __name__ == "__main__":
    main()
