"""Una foto de verdad por Cloudflare, para ver si sirve antes de fiarse.

Cuesta unas 110 neuronas de las 10.000 del día: un 1%. Genera dos escenas,
las pasa por el mismo revisor que el reel —calidad e identidad— y escribe el
resultado en `cloudflare/informe.md`, con las fotos al lado, salgan como
salgan. Lo importante es poder MIRARLAS: los números no dicen si es Allie.

Se lanza a mano desde la pestaña Actions. Si faltan las credenciales lo dice
y se para sin fallar, para que el aviso se lea en vez de parecer una avería.
"""
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloudflare  # noqa: E402
import gemini  # noqa: E402
import reel  # noqa: E402

CARPETA = Path(__file__).resolve().parent.parent / "cloudflare"

ESCENAS = [
    "sitting at a window table in a sunny Madrid café, holding a coffee cup, "
    "looking out of the window",
    "walking along a tree-lined street in autumn, wearing a beige coat, "
    "smiling at the camera",
]


def main():
    CARPETA.mkdir(exist_ok=True)
    ahora = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    lineas = [f"# Prueba de Cloudflare · {ahora} UTC", ""]

    if not cloudflare.hay():
        lineas += [
            "**No hay credenciales.** Faltan los secretos `CF_ACCOUNT_ID` y "
            "`CF_API_TOKEN` en Settings → Secrets and variables → Actions.",
            "",
            "Mientras no estén, Allie sigue dependiendo de Hugging Face, que "
            "lleva desde el 11 de octubre sin dar ni una foto.",
        ]
        (CARPETA / "informe.md").write_text("\n".join(lineas), encoding="utf-8")
        print("\n".join(lineas), flush=True)
        return

    p = reel.persona()
    referencia = reel.referencia_bytes(p)
    if not referencia:
        lineas.append("No se pudo traer la foto de referencia de Allie.")
        (CARPETA / "informe.md").write_text("\n".join(lineas), encoding="utf-8")
        sys.exit(1)

    buenas = 0
    for i, escena in enumerate(ESCENAS, 1):
        orden = (
            f"Keep her face, hair, skin tone and body exactly as they are — it must be "
            f"unmistakably the same woman. Place her in this scene: {escena}. "
            f"{reel.CARA}. {reel.ANATOMIA}. Photorealistic smartphone photo, soft natural "
            f"light. No text, no logos and no watermark anywhere in the image.")
        lineas += [f"## {i} · {escena}", ""]
        try:
            datos, segundos, modelo = cloudflare.generar(referencia, orden)
        except Exception as e:  # noqa: BLE001
            lineas += [f"Reventó: `{type(e).__name__}: {e}`", "",
                       "```", traceback.format_exc()[-1200:], "```", ""]
            continue

        if not datos:
            for m in (modelo or []):
                lineas.append(f"- no salió · {m}")
            lineas.append("")
            continue

        nombre = f"{ahora}-{i}.jpg"
        (CARPETA / nombre).write_bytes(datos)
        lineas += [f"![{nombre}]({nombre})", "",
                   f"- modelo: `{modelo}`", f"- tardó: {segundos}s", ""]

        try:
            ok, problema = gemini.revisar_imagen(datos, referencia=referencia)
        except Exception as e:  # noqa: BLE001
            ok, problema = False, f"el revisor falló: {type(e).__name__}: {e}"
        lineas += [f"- revisor: **{'pasa' if ok else 'NO pasa'}**"
                   + (f" · {problema}" if problema else ""), ""]
        if ok:
            buenas += 1

    lineas += ["---", "",
               f"**{buenas} de {len(ESCENAS)} pasaron el revisor.**", "",
               "Si las fotos son Allie, Cloudflare puede sustituir a Hugging Face: "
               "unas noventa fotos al día en vez de ninguna.", ""]
    (CARPETA / "informe.md").write_text("\n".join(lineas), encoding="utf-8")
    print("\n".join(lineas), flush=True)


if __name__ == "__main__":
    main()
