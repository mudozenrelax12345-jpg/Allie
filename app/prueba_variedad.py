"""Que Allie no salga siempre con el mismo jersey beige.

EL FALLO. El 18 de octubre, 81 fotos en el banco y diecisiete con el mismo
jersey de punto beige, nueve con la camisa de lino blanca y nueve con la
gabardina. Teresa lo vio en el perfil en diez segundos; yo no lo había
mirado nunca.

La causa no era el generador de imágenes: era que a quien escribe las
escenas no se le decía qué ropa poner, así que la elegía él. Y un modelo de
lenguaje que elige libremente elige siempre lo mismo. La solución no es
pedirle variedad —eso ya se lo pedíamos—, es quitarle la decisión.

Esta prueba fija las cuatro cosas que tienen que seguir siendo verdad:
  1. la prenda va escrita en la orden, palabra por palabra;
  2. en veinte tandas seguidas no se repite casi nada;
  3. la ropa cuadra con la estación: ni plumífero en julio ni lino en enero;
  4. queda apuntado en el índice qué se usó, que es lo que permite (2).
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contexto  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(f"{'ok  ' if bien else 'MAL '} {que}" + (f" · {detalle}" if detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


def main():
    # 1 · La prenda viaja escrita dentro de la orden.
    import banco
    capturado = {}

    def falso_json(prompt, **kw):
        capturado["prompt"] = prompt
        return {"escenas": ["The same woman, de prueba"] * 3}

    banco.gemini.json_ = falso_json
    vestuario = ("burdeos-blazer", "an oversized burgundy wool blazer over a black top", "oi")
    sitio = ("retiro", "walking under the plane trees in el Retiro park", "iopv")
    banco.escenas({"nombre": "Allie"}, 3, "un paseo", vestuario, sitio)
    comprobar("la prenda concreta va dentro de la orden",
              vestuario[1] in capturado.get("prompt", ""))
    comprobar("y el sitio concreto también",
              sitio[1] in capturado.get("prompt", ""))
    comprobar("y se le prohíbe cambiarla",
              "No lo cambies" in capturado.get("prompt", ""))

    # 2 · Veinte tandas seguidas sin repetirse.
    usados_v, usados_s = [], []
    for i in range(20):
        v, s = contexto.elegir("o", usados_v[:8], usados_s[:8], semilla=i)
        usados_v.insert(0, v[0])
        usados_s.insert(0, s[0])
    comprobar("al menos 12 prendas distintas en 20 tandas",
              len(set(usados_v)) >= 12, f"{len(set(usados_v))} distintas")
    comprobar("al menos 12 sitios distintos en 20 tandas",
              len(set(usados_s)) >= 12, f"{len(set(usados_s))} distintos")
    repetida_cerca = any(usados_v[i] in usados_v[i + 1:i + 6] for i in range(15))
    comprobar("ninguna prenda se repite dentro de cinco tandas",
              not repetida_cerca)

    # 3 · La ropa cuadra con la estación.
    verano = {v[0] for v in contexto.VESTUARIO if "v" in v[2]}
    invierno = {v[0] for v in contexto.VESTUARIO if "i" in v[2]}
    comprobar("el plumífero no es ropa de verano", "plumifero" not in verano)
    comprobar("el abrigo de lana no es ropa de verano", "camel-abrigo" not in verano)
    comprobar("hay ropa suficiente en cada estación",
              min(len([v for v in contexto.VESTUARIO if e in v[2]])
                  for e in "iopv") >= 8,
              str({e: len([v for v in contexto.VESTUARIO if e in v[2]]) for e in "iopv"}))

    # 4 · El índice guarda lo usado, que es de donde sale la memoria.
    indice = {"fotos": [
        {"vestuario": "verde-cuello", "sitio": "retiro", "creada": "2026-10-18T10:00:00"},
        {"vestuario": "cuero-negro", "sitio": "malasana", "creada": "2026-10-17T10:00:00"},
    ]}
    v, s = contexto.ultimos(indice)
    comprobar("el índice recuerda lo último puesto",
              v[:2] == ["verde-cuello", "cuero-negro"], str(v))
    comprobar("y lo último visitado", s[:2] == ["retiro", "malasana"], str(s))

    # 5 · El calendario sitúa a Allie en el año, no en un octubre eterno.
    texto, letra = contexto.momento(date(2026, 12, 23))
    comprobar("en diciembre sabe que es invierno", letra == "i", texto[:60])
    comprobar("y que vienen las fechas de Navidad",
              "Nochebuena" in texto or "Navidad" in texto, texto)
    texto_v, letra_v = contexto.momento(date(2026, 7, 14))
    comprobar("en julio sabe que es verano", letra_v == "v", texto_v[:60])

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nAllie se cambia de ropa.", flush=True)


if __name__ == "__main__":
    main()
