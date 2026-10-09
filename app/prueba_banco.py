"""Comprueba que el banco reparte bien, sin tocar el banco de verdad.

Lo que se prueba es lo que se puede notar en Instagram si falla: que un
carrusel salga con fotos de sitios distintos, que se repita una foto ya
publicada, o que un fallo de subida se coma fotos que nunca salieron.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import banco  # noqa: E402

fallos = []


def comprobar(que, bien):
    print(("ok   " if bien else "MAL  ") + que, flush=True)
    if not bien:
        fallos.append(que)


def preparar(tmp):
    """Un banco de mentira: dos tandas de casa y una de calle."""
    banco.BANCO = Path(tmp)
    banco.FOTOS = Path(tmp) / "fotos"
    banco.INDICE = Path(tmp) / "indice.json"
    banco.FOTOS.mkdir(parents=True, exist_ok=True)
    fotos = []
    for tanda, etiqueta, cuantas, creada in (
            ("20260101-1000", "casa", 3, "2026-01-01T10:00"),
            ("20260202-1000", "casa", 2, "2026-02-02T10:00"),
            ("20260303-1000", "calle", 4, "2026-03-03T10:00")):
        for i in range(1, cuantas + 1):
            nombre = f"{tanda}-{i}.jpg"
            (banco.FOTOS / nombre).write_bytes(b"x" * 10)
            fotos.append({"archivo": nombre, "tanda": tanda,
                          "etiqueta": etiqueta, "tema": etiqueta,
                          "escena": "", "usada": None, "creada": creada})
    banco.INDICE.write_text(json.dumps({"fotos": fotos}), encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        preparar(tmp)

        comprobar("hay 9 libres al empezar",
                  len(banco.disponibles(banco.leer())) == 9)

        # Un carrusel tiene que salir de una sola tanda: misma ropa y sitio.
        cogidas, _ = banco.coger(3, "casa")
        tandas = {Path(c).name.rsplit("-", 1)[0] for c in cogidas}
        comprobar("3 de casa salen de una sola tanda",
                  len(cogidas) == 3 and len(tandas) == 1)
        comprobar("coge la tanda más antigua que da el número",
                  tandas == {"20260101-1000"})

        # Y no puede volver a darlas.
        comprobar("las cogidas quedan marcadas como usadas",
                  len(banco.disponibles(banco.leer())) == 6)
        otras, _ = banco.coger(2, "casa")
        comprobar("no repite fotos ya usadas",
                  not ({Path(o).name for o in otras} & {Path(c).name for c in cogidas}))

        # La etiqueta se respeta: una foto de calle en un post de casa canta.
        calle, _ = banco.coger(4, "calle")
        comprobar("la etiqueta se respeta",
                  all("20260303" in Path(c).name for c in calle))

        # Pedir más de lo que hay devuelve lo que haya, no revienta.
        resto, _ = banco.coger(5, "casa")
        comprobar("pedir de más no revienta", isinstance(resto, list))

        # Y si la publicación no sale, las fotos vuelven a estar libres.
        antes = len(banco.disponibles(banco.leer()))
        banco.devolver(calle)
        comprobar("devolver libera las fotos no publicadas",
                  len(banco.disponibles(banco.leer())) == antes + len(calle))

        # Una foto cuyo archivo ya no está no se puede ofrecer.
        (banco.FOTOS / "20260303-1000-1.jpg").unlink()
        comprobar("una foto sin archivo no se ofrece",
                  all(f["archivo"] != "20260303-1000-1.jpg"
                      for f in banco.disponibles(banco.leer())))

        # Un índice ilegible no debe tumbar la publicación del día.
        banco.INDICE.write_text("{ esto no es json", encoding="utf-8")
        comprobar("un índice roto no revienta",
                  banco.leer() == {"fotos": []} and banco.coger(2)[0] == [])

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nel banco reparte bien", flush=True)


if __name__ == "__main__":
    main()
