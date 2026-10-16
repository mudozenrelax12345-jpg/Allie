"""Comprueba que el texto del post se escribe MIRANDO las fotos.

De dónde sale. El 15 de octubre el reel salió programado con este texto:
«Entre brochas, colores y alguna que otra mancha de pintura que ya forma
parte del outfit». Las tres fotos eran Allie sentada en una cafetería con un
jersey de punto. Ni un pincel, ni una gota de pintura.

No fue mala suerte. guion() escribe el texto ANTES de que exista ninguna
foto, a partir de un tema elegido al azar, y luego el vídeo se monta con
fotos del banco que pueden ser de otro tema. El texto y las imágenes nunca
se habían visto.

Lo que se comprueba aquí es lo único que importa: que las fotos LLEGUEN a
quien escribe el texto, y que si eso falla se note en el registro en vez de
publicarse un texto inventado como si nada.

No llama a Gemini: sustituye la llamada por una de mentira.
"""
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402
import reel  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que
          + (f"  ·  {detalle}" if not bien and detalle else ""), flush=True)
    if not bien:
        fallos.append(que)


def main():
    carpeta = Path(tempfile.mkdtemp(prefix="reel-texto-"))
    rutas = []
    for i in range(1, 4):
        r = carpeta / f"foto{i}.jpg"
        Image.new("RGB", (120, 150), (40 * i, 80, 120)).save(r, "JPEG")
        rutas.append(r)

    p = {"nombre": "Allie", "personalidad": "cercana", "hashtags_base": ["#Allie"]}
    visto = {}

    def falso_json(prompt, imagenes=()):
        visto["imagenes"] = list(imagenes)
        visto["prompt"] = prompt
        return {"texto": "texto escrito con las fotos delante",
                "hashtags": ["#Allie", "#Madrid"], "idea": "una idea"}

    orig = gemini.json_
    gemini.json_ = falso_json
    try:
        g = reel.texto_de_las_fotos(p, rutas, "idea previa")

        comprobar("las fotos llegan a quien escribe el texto",
                  len(visto.get("imagenes") or []) == 3,
                  f"llegaron {len(visto.get('imagenes') or [])}")
        comprobar("y llegan como bytes de imagen, no como rutas",
                  all(isinstance(b, bytes) and b[:2] == b"\xff\xd8"
                      for b in visto.get("imagenes") or []))
        comprobar("el encargo prohíbe inventar lo que no se ve",
                  "se vean en las fotos" in (visto.get("prompt") or "")
                  or "SE VEAN" in (visto.get("prompt") or ""),
                  (visto.get("prompt") or "")[:120])
        comprobar("devuelve el texto nuevo",
                  (g or {}).get("texto") == "texto escrito con las fotos delante",
                  str(g)[:100])

        # Si Gemini se cae, NO se inventa nada: se devuelve None y quien llama
        # se queda con el texto viejo, avisando en el registro.
        def se_cae(prompt, imagenes=()):
            raise RuntimeError("Gemini caído")

        gemini.json_ = se_cae
        comprobar("si el revisor de texto falla, no inventa nada",
                  reel.texto_de_las_fotos(p, rutas, "") is None)

        # Y si no hay fotos legibles, tampoco.
        gemini.json_ = falso_json
        comprobar("sin fotos que mirar, no escribe",
                  reel.texto_de_las_fotos(p, [carpeta / "no-existe.jpg"], "") is None)

        # Un texto vacío de Gemini no vale como texto.
        gemini.json_ = lambda prompt, imagenes=(): {"texto": "   "}
        comprobar("un texto en blanco no cuenta como texto",
                  reel.texto_de_las_fotos(p, rutas, "") is None)
    finally:
        gemini.json_ = orig
        import shutil
        shutil.rmtree(carpeta, ignore_errors=True)

    # guion_del_banco tiene que ENCONTRAR las escenas en el apunte real.
    # Leer una clave que no existe no da error: deja el texto vacío y el
    # reel sale publicable y mudo, que es peor que fallar.
    import json as _json
    tmp = Path(tempfile.mkdtemp(prefix="banco-apunte-"))
    guardados = (reel.VIDEOS, reel.BASE)
    try:
        (tmp / "videos").mkdir(); (tmp / "banco").mkdir()
        (tmp / "videos" / "del-banco.json").write_text(_json.dumps(
            {"cuando": "2026-10-16T14:41:32", "cogidas": ["a-1.jpg", "a-2.jpg"]}),
            encoding="utf-8")
        (tmp / "banco" / "indice.json").write_text(_json.dumps({"fotos": [
            {"archivo": "a-1.jpg", "tanda": "a", "tema": "paseo por el barrio",
             "escena": "The same woman, medium shot, walking down a cobbled street"},
            {"archivo": "a-2.jpg", "tanda": "a", "tema": "paseo por el barrio",
             "escena": "The same woman, close-up, autumn light on her face"}]}),
            encoding="utf-8")
        reel.VIDEOS, reel.BASE = tmp / "videos", tmp

        visto.clear()
        gemini.json_ = falso_json
        g2 = reel.guion_del_banco({"nombre": "Allie", "hashtags_base": ["#Allie"]})
        comprobar("guion_del_banco encuentra las fotos del apunte real",
                  "cobbled street" in (visto.get("prompt") or ""),
                  (visto.get("prompt") or "(no llamó a nadie)")[:140])
        comprobar("y usa el tema de las fotos, no uno al azar",
                  g2.get("tema") == "paseo por el barrio", str(g2.get("tema")))
        comprobar("y devuelve texto", bool((g2 or {}).get("texto")), str(g2)[:80])
    finally:
        reel.VIDEOS, reel.BASE = guardados
        gemini.json_ = orig
        import shutil as _sh
        _sh.rmtree(tmp, ignore_errors=True)

    # Y la comprobación del montaje: que main() use lo que devuelve esto.
    fuente = (Path(__file__).resolve().parent / "reel.py").read_text(encoding="utf-8")
    trozo = fuente.split("def main():", 1)[-1]
    comprobar("main() reescribe el texto antes de montar",
              "texto_de_las_fotos(" in trozo
              and trozo.index("texto_de_las_fotos(") < trozo.index("componer(rutas)"))

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nel texto se escribe mirando las fotos", flush=True)


if __name__ == "__main__":
    main()
