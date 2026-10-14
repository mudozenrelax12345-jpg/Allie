"""Comprueba que dos fotos no pueden pisarse en el banco.

De dónde sale. El 14 de octubre, el primer día que Cloudflare funcionó, el
banco dijo «metidas: 3» y en disco solo había 2. El índice tenía dos fichas
distintas —escenas distintas— apuntando al MISMO archivo: una foto generada,
pagada y aprobada por el revisor, desaparecida.

El motivo: el nombre de la tanda se formaba con la hora al minuto, y main()
llama a llenar() una vez por tema. Con Hugging Face cada foto tardaba
minutos y nunca coincidían. Con Cloudflare tarda ocho segundos, así que dos
temas caen dentro del mismo minuto, comparten nombre de tanda y la segunda
foto escribe encima de la primera.

Es un fallo que solo aparece cuando todo va bien, que son los peores: no
avisa, no sale en ningún registro, y lo único que se ve es un número que no
cuadra con lo que hay.

No genera nada: sustituye el generador y el revisor por unos de mentira.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import banco  # noqa: E402
import gemini  # noqa: E402
import reel  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que
          + (f"  ·  {detalle}" if not bien and detalle else ""), flush=True)
    if not bien:
        fallos.append(que)


def main():
    temporal = Path(tempfile.mkdtemp(prefix="banco-prueba-"))
    fotos, indice = temporal / "fotos", temporal / "indice.json"
    fotos.mkdir()

    # Todo de mentira menos lo que se está probando.
    guardados = (banco.FOTOS, banco.INDICE, reel.kontext, gemini.revisar_imagen,
                 reel.referencia_bytes, banco.escenas)
    banco.FOTOS, banco.INDICE = fotos, indice
    hechas = []

    def falso_kontext(escena, p):
        hechas.append(escena)
        # Cada foto con un contenido distinto, para ver si alguna se pierde.
        return (f"FOTO {len(hechas)}".encode() + b"\x00" * 50), None

    reel.kontext = falso_kontext
    gemini.revisar_imagen = lambda datos, referencia=None: (True, "")
    reel.referencia_bytes = lambda p: b"referencia"
    banco.escenas = lambda p, cuantas, tema: [f"escena de {tema} {n}"
                                              for n in range(1, cuantas + 1)]

    try:
        # Dos temas seguidos, que es exactamente lo que hace main(). Se
        # ejecutan en el mismo segundo, mucho peor que el caso real.
        total = 0
        for tema in ("un café por la mañana", "un paseo por el barrio"):
            metidas, _ = banco.llenar(cuantas=2, tema=tema)
            total += metidas

        en_disco = sorted(f.name for f in fotos.iterdir())
        fichas = json.loads(indice.read_text())["fotos"]

        comprobar("dice haber metido 4", total == 4, f"dijo {total}")
        comprobar("y hay 4 ficheros de verdad en el banco",
                  len(en_disco) == 4, f"{en_disco}")
        comprobar("ninguna ficha del índice repite archivo",
                  len({f["archivo"] for f in fichas}) == len(fichas),
                  f"{[f['archivo'] for f in fichas]}")
        comprobar("cada ficha apunta a un fichero que existe",
                  all((fotos / f["archivo"]).exists() for f in fichas),
                  f"{[f['archivo'] for f in fichas]}")

        # Y lo que de verdad importa: que no se haya perdido el contenido.
        contenidos = {(fotos / f["archivo"]).read_bytes()[:7] for f in fichas}
        comprobar("las 4 fotos son distintas, ninguna pisada",
                  len(contenidos) == 4, f"{sorted(contenidos)}")

        # Las dos tandas tienen que poder distinguirse, que es para lo que
        # sirven: un carrusel se arma con fotos de la misma ropa y sitio.
        comprobar("las dos tandas quedan separadas",
                  len({f["tanda"] for f in fichas}) == 2,
                  f"{sorted({f['tanda'] for f in fichas})}")
    finally:
        (banco.FOTOS, banco.INDICE, reel.kontext, gemini.revisar_imagen,
         reel.referencia_bytes, banco.escenas) = guardados
        shutil.rmtree(temporal, ignore_errors=True)

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nninguna foto se pisa con otra", flush=True)


if __name__ == "__main__":
    main()
