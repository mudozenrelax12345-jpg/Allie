"""Comprueba que en un repositorio público no se publican datos de nadie.

De dónde sale. El 13 de octubre se agotaron los 2.000 minutos mensuales de
GitHub Actions y todo dejó de ejecutarse. La salida es poner los
repositorios en público, donde Actions es gratis e ilimitado. Pero en un
repositorio público los REGISTROS y las INCIDENCIAS los lee cualquiera, y
este bot maneja nombres de usuario y mensajes privados de personas reales.

Lo que se comprueba:
  · en público, los nombres salen tapados y los mensajes privados no se
    copian a ninguna incidencia
  · en privado, todo sigue como estaba, que si no la herramienta deja de
    servir para lo que sirve
  · y que nadie vuelva a meter un `@{autor}` sin tapar en un sitio que
    pueda acabar publicado

No llama a Instagram ni a Gemini.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que
          + (f"  ·  {detalle}" if not bien and detalle else ""), flush=True)
    if not bien:
        fallos.append(que)


def en_modo(privado, codigo):
    """Ejecuta `codigo` con main importado en el modo pedido."""
    entorno = dict(os.environ)
    entorno["REPO_PRIVADO"] = "true" if privado else "false"
    for v in ("GEMINI_API_KEY", "HF_TOKEN", "CF_API_TOKEN"):
        entorno.pop(v, None)
    r = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(APP)!r}); import main; {codigo}"],
        env=entorno, capture_output=True, text=True, timeout=120)
    return (r.stdout + r.stderr).strip()


def main():
    # 1 · En público, el nombre se tapa.
    r = en_modo(False, "print(main.quien('mariagarcia'))")
    comprobar("en público el nombre sale tapado",
              r.startswith("mar") and "mariagarcia" not in r and "•" in r, r)
    comprobar("y se tapa entero, no solo un trozo",
              "garcia" not in r and "ia" not in r[3:].replace("•", ""), r)

    # 2 · En privado, no se toca nada: la herramienta tiene que seguir siendo útil.
    r = en_modo(True, "print(main.quien('mariagarcia'))")
    comprobar("en privado el nombre va entero", r == "mariagarcia", r)

    # 3 · Si no se sabe si es público o privado, se tapa. Equivocarse hacia el
    #     lado discreto no cuesta nada; al revés, publica datos de alguien.
    entorno = dict(os.environ)
    entorno.pop("REPO_PRIVADO", None)
    r = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(APP)!r}); import main;"
         f" print(main.PRIVADO, main.quien('mariagarcia'))"],
        env=entorno, capture_output=True, text=True, timeout=120)
    salida = (r.stdout + r.stderr).strip()
    comprobar("sin saberlo, se asume público y se tapa",
              salida.startswith("False") and "mariagarcia" not in salida, salida)

    # 4 · Revisión del código: que no quede ningún nombre sin tapar camino de
    #     un registro o de una incidencia.
    fuente = (APP / "main.py").read_text(encoding="utf-8")
    crudos = []
    for n, linea in enumerate(fuente.splitlines(), 1):
        if re.search(r"(log\(|gh\.issue\()", linea) or re.search(r"^\s+f?\"", linea):
            if re.search(r"\{autor\}|@\{autor", linea):
                crudos.append(f"línea {n}: {linea.strip()[:70]}")
    comprobar("ningún @{autor} sin tapar en registros ni incidencias",
              not crudos, " | ".join(crudos))

    # 5 · El volcado en crudo de Instagram no se ejecuta en público.
    fuente_diag = fuente.split("def diagnostico(", 1)[-1][:1800]
    comprobar("el volcado en crudo está protegido",
              "if not PRIVADO:" in fuente_diag and "return" in fuente_diag,
              fuente_diag[:120])

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nen público no se publican datos de nadie", flush=True)


if __name__ == "__main__":
    main()
