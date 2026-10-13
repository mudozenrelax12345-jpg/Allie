"""Comprueba que un modelo de Gemini caído no tumba el trabajo entero.

Hay seis modelos de texto en la lista justamente para esto. El martes 13 el
reel se perdió porque Gemini contestó «gemini-3.5-flash-lite is currently
experiencing high demand» y el código hizo `raise` con el primero sin
probar los otros cinco: ese mensaje no encajaba en ninguna de las palabras
que marcaban «sin cupo».

Son dos situaciones distintas y hay que tratarlas distinto:
  · sin cupo   → este modelo no va hoy, se descarta para el resto del rato
  · saturado   → existe y tiene cupo, pero ahora no atiende; se pasa al
                 siguiente y NO se descarta, porque vuelve solo

No llama a Gemini: sustituye la llamada por una de mentira.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que
          + (f"  ·  {detalle}" if not bien and detalle else ""), flush=True)
    if not bien:
        fallos.append(que)


def con_respuestas(respuestas, prueba):
    """`respuestas` decide qué hace cada modelo: una excepción o un texto."""
    orig, pedidos = gemini._una_vez, []

    def falso(modelo, prompt, imagenes):
        pedidos.append(modelo)
        r = respuestas.get(modelo, respuestas.get("*"))
        if isinstance(r, Exception):
            raise r
        return {"outputs": [{"content": [{"type": "text", "text": r}]}]}

    gemini._una_vez = falso
    gemini._elegido = None
    gemini._descartados.clear()
    try:
        return prueba(), pedidos
    finally:
        gemini._una_vez = orig


SATURADO = gemini.GeminiError(
    "Gemini: gemini-3.5-flash-lite is currently experiencing high demand, "
    "spikes in demand are usually temporary. Please try again later.")
SIN_CUPO = gemini.GeminiError("Gemini: 429 RESOURCE_EXHAUSTED quota exceeded")


def main():
    primero = gemini.MODELOS[0]
    segundo = gemini.MODELOS[1]

    # 1 · El caso que tiró el reel: el primero saturado, el segundo bien.
    def pedir():
        try:
            return gemini.texto("hola")
        except Exception as e:  # noqa: BLE001
            return f"{type(e).__name__}: {str(e)[:80]}"

    r, pedidos = con_respuestas({primero: SATURADO, "*": "sale bien"}, pedir)
    comprobar("un modelo saturado no tumba la llamada", r == "sale bien", r)
    comprobar("y se prueba el siguiente de la lista",
              len(pedidos) >= 2 and pedidos[0] == primero, f"{pedidos}")
    comprobar("el saturado NO se descarta: vuelve solo",
              primero not in gemini._descartados,
              f"descartados={gemini._descartados}")

    # 2 · Sin cupo sí se descarta, para no gastar intentos el resto del rato.
    r, pedidos = con_respuestas({primero: SIN_CUPO, "*": "sale bien"}, pedir)
    comprobar("sin cupo también sigue adelante", r == "sale bien", r)
    comprobar("y ese sí queda descartado", primero in gemini._descartados,
              f"descartados={gemini._descartados}")

    # 3 · Si TODOS están saturados, se avisa con claridad en vez de callar.
    r, _ = con_respuestas({"*": SATURADO}, pedir)
    comprobar("si fallan todos, el error lo dice", "GeminiError" in r, r)

    # 4 · Un error que no es ni cupo ni saturación sube tal cual: si la clave
    # está mal, enterarse rápido es mejor que probar seis veces.
    r, pedidos = con_respuestas(
        {"*": gemini.GeminiError("Gemini: API key not valid")}, pedir)
    comprobar("una clave inválida no se disfraza de otra cosa",
              "not valid" in r, r)
    comprobar("y no se prueban los seis modelos por nada",
              len(pedidos) == 1, f"probó {pedidos}")

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nun modelo caído no tumba el trabajo", flush=True)


if __name__ == "__main__":
    main()
