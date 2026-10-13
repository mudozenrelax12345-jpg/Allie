"""Comprueba que los programas arrancan con los inputs vacíos.

De dónde sale. GitHub pasa los inputs de workflow_dispatch como variables de
entorno, y en una ejecución programada no los deja sin poner: los pone en
cadena vacía. `int(os.environ.get("CUANTAS", "9"))` recibe entonces "" y
revienta, porque el valor por omisión solo se aplica si la variable no está.

El banco de fotos se cayó así la primera noche, a las 04:20, con la cuota
recién renovada y nadie mirando. El fallo no estaba en lo difícil —generar y
revisar fotos— sino en la primera línea.

Esto pone a vacío todas las variables que los workflows pasan e importa los
módulos. Si alguno vuelve a reventar al arrancar, salta aquí y no de noche.
"""
import os
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
BASE = APP.parent

# Todo lo que los workflows pasan por `env:` desde `inputs`, que es
# precisamente lo que llega vacío cuando el trabajo lo lanza el reloj.
VACIAS = ["TEMA", "TEMAS", "CUANTAS", "CUANTAS_FOTOS", "FOTOS_POR_POST", "FOTOS",
          "FOTOS_REEL", "ETIQUETA",
          "SOLO_MONTAR", "SOLO_SUBIR", "TOPE_ESPACIOS", "ESPERA_ESPACIO",
          "PRODUCTO", "REPO_PRIVADO", "CF_ANCHO", "CF_ALTO", "CF_MODELOS"]

MODULOS = ["ajustes", "cloudflare", "espacio", "reel", "foto", "banco", "semana", "buscar_espacios",
           "subir_banco", "del_banco_a_fotos", "devolver_fotos",
           "prueba_ugc", "falta_reel", "probar_gemini", "prueba_cuota", "prueba_gemini_caida", "prueba_cloudflare",
           "prueba_discrecion"]


def main():
    entorno = dict(os.environ)
    for v in VACIAS:
        entorno[v] = ""
    # Sin credenciales: arrancar no debe necesitarlas. Si un módulo las pide
    # al importarse, eso también es un fallo que quiero ver aquí.
    for v in ("GEMINI_API_KEY", "POLLINATIONS_KEY", "HF_TOKEN",
              "CF_ACCOUNT_ID", "CF_API_TOKEN"):
        entorno.pop(v, None)

    fallos = []
    for m in MODULOS:
        r = subprocess.run(
            [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(APP)!r});"
                                   f" import {m}; print('ok')"],
            env=entorno, cwd=str(BASE), capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            print(f"ok   {m} arranca con los inputs vacíos", flush=True)
        else:
            ultima = (r.stderr.strip().splitlines() or ["sin mensaje"])[-1]
            print(f"MAL  {m}: {ultima}", flush=True)
            fallos.append(m)

    # Y el lector de ajustes, por su cuenta.
    sys.path.insert(0, str(APP))
    import ajustes
    casos = [
        ("vacío da el valor por omisión", lambda: ajustes.entero("CUANTAS", 9) == 9),
        ("un número se lee", lambda: (os.environ.update({"CUANTAS": "4"}),
                                      ajustes.entero("CUANTAS", 9) == 4)[1]),
        ("espacios cuentan como vacío", lambda: (os.environ.update({"CUANTAS": "  "}),
                                                 ajustes.entero("CUANTAS", 9) == 9)[1]),
        ("texto no numérico no revienta", lambda: (os.environ.update({"CUANTAS": "ocho"}),
                                                   ajustes.entero("CUANTAS", 9) == 9)[1]),
        ("lista vacía es lista vacía", lambda: (os.environ.update({"TEMAS": ""}),
                                                ajustes.lista("TEMAS") == [])[1]),
    ]
    for que, prueba in casos:
        try:
            bien = bool(prueba())
        except Exception as e:  # noqa: BLE001
            bien, que = False, f"{que} ({type(e).__name__}: {e})"
        print(("ok   " if bien else "MAL  ") + que, flush=True)
        if not bien:
            fallos.append(que)

    if fallos:
        print(f"\n{len(fallos)} cosas mal: {', '.join(map(str, fallos))}", flush=True)
        sys.exit(1)
    print("\ntodo arranca con los inputs vacíos", flush=True)


if __name__ == "__main__":
    main()
