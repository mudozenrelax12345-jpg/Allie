"""Comprueba las barreras del publicador antes de que toquen la cuenta real.

Publicar no se deshace. Esto comprueba, sin llamar a Instagram, que:
  · no se publica un reel sin texto (saldría un vídeo mudo),
  · no se publica dos veces el mismo vídeo,
  · el texto lleva siempre la declaración de IA, y una sola vez,
  · y que la dirección del vídeo apunta al repositorio, no a un
    alojamiento temporal de los que caducan en horas.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publicar  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que + (f"  ·  {detalle}" if not bien and detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


def con_ultimo(d, registro=None):
    tmp = Path(tempfile.mkdtemp(prefix="publicar-"))
    (tmp / "videos").mkdir()
    if d.get("archivo"):
        (tmp / "videos" / d["archivo"]).write_bytes(b"x" * 100)
    (tmp / "videos" / "ultimo.json").write_text(json.dumps(d), encoding="utf-8")
    if registro is not None:
        (tmp / "videos" / "publicados.json").write_text(json.dumps(registro), encoding="utf-8")
    publicar.BASE = tmp
    publicar.ULTIMO = tmp / "videos" / "ultimo.json"
    publicar.REGISTRO = tmp / "videos" / "publicados.json"
    return tmp


def main():
    import os
    os.environ["EN_SECO"] = "si"

    # 1 · Sin texto no se publica.
    con_ultimo({"archivo": "r.mp4", "texto": "   ", "hashtags": "#Allie"})
    try:
        publicar.main()
        comprobar("un reel sin texto no se publica", False, "lo dejó pasar")
    except RuntimeError as e:
        comprobar("un reel sin texto no se publica", "mudo" in str(e), str(e)[:80])

    # 2 · Lo ya publicado no se repite.
    con_ultimo({"archivo": "r.mp4", "texto": "hola", "hashtags": "#Allie"},
               registro=[{"archivo": "r.mp4", "media_id": "1"}])
    try:
        publicar.main()
        comprobar("no se publica dos veces el mismo vídeo", True)
    except Exception as e:  # noqa: BLE001
        comprobar("no se publica dos veces el mismo vídeo", False, str(e)[:80])

    # 3 · Si falta el fichero, no se intenta.
    con_ultimo({"archivo": "", "texto": "hola"})
    try:
        publicar.main()
        comprobar("sin fichero no se intenta", False, "lo dejó pasar")
    except RuntimeError:
        comprobar("sin fichero no se intenta", True)

    # 4 · La declaración de IA, siempre y una sola vez.
    t = publicar.con_aviso("Qué tarde tan buena.", "#Allie #Madrid")
    comprobar("el texto lleva la declaración de IA", "generado con IA" in t, t)
    comprobar("y los hashtags", "#Madrid" in t, t)
    # Lo que de verdad importa: que se vea ANTES del «… más» de Instagram,
    # que corta sobre los 125 caracteres. Al final no la lee nadie.
    comprobar("la declaración se ve sin desplegar el pie",
              "generado con IA" in t[:publicar.LIMITE_VISIBLE],
              f"aparece en el carácter {t.find('generado con IA')}")
    comprobar("y es lo primero que se lee", t.strip().startswith("🤖"), t[:40])
    largo = publicar.con_aviso("x" * 400, "#Allie")
    comprobar("también con un texto largo",
              "generado con IA" in largo[:publicar.LIMITE_VISIBLE],
              f"carácter {largo.find('generado con IA')}")
    t2 = publicar.con_aviso("Esto ya dice que es contenido generado con IA desde el principio.",
                            "#Allie")
    comprobar("no se repite si ya estaba al principio",
              t2.count("generado con IA") == 1, t2)

    # 5 · La dirección del vídeo es la del repositorio.
    comprobar("el vídeo se sirve desde el repositorio público",
              publicar.CRUDO.startswith("https://raw.githubusercontent.com/")
              and "/Allie/main/videos/" in publicar.CRUDO, publicar.CRUDO)

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal", flush=True)
        sys.exit(1)
    print("\nlas barreras del publicador aguantan", flush=True)


if __name__ == "__main__":
    main()
