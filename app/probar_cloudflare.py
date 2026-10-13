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


def interrogar():
    """Si falla, preguntarle a Cloudflare POR QUÉ, en vez de adivinar.

    Un 401 puede ser tres cosas muy distintas y se arreglan de tres maneras
    distintas: el token está mal copiado, el token es válido pero no tiene
    permiso de Workers AI, o el token es de otra cuenta. Cloudflare tiene dos
    endpoints que lo separan, y ninguno gasta neuronas.
    """
    import requests

    cuenta, ficha = cloudflare.credenciales()
    cab = {"Authorization": f"Bearer {ficha}"}
    fuera = ["### Qué dice Cloudflare del token", "",
             f"- longitud del token: **{len(ficha or '')}** caracteres "
             f"(lo normal son unos 40; mucho menos = se copió a medias)",
             f"- Account ID configurado: `{(cuenta or '')[:6]}…{(cuenta or '')[-4:]}` "
             f"({len(cuenta or '')} caracteres)"]

    # 1 · ¿El token existe y está activo? Esto no depende de la cuenta.
    try:
        r = requests.get("https://api.cloudflare.com/client/v4/user/tokens/verify",
                         headers=cab, timeout=60)
        c = r.json()
        if c.get("success"):
            fuera.append(f"- el token **es válido y está activo** "
                         f"(estado: {(c.get('result') or {}).get('status')})")
            valido = True
        else:
            fuera.append(f"- el token **NO vale**: {str(c.get('errors'))[:200]}")
            valido = False
    except Exception as e:  # noqa: BLE001
        fuera.append(f"- no se pudo comprobar el token: {type(e).__name__}: {e}")
        valido = None

    # 2 · ¿A qué cuentas puede entrar? Si la nuestra no está, el fallo es que
    #     el token se hizo en otra cuenta o se limitó a otra.
    try:
        r = requests.get("https://api.cloudflare.com/client/v4/accounts",
                         headers=cab, timeout=60)
        c = r.json()
        if c.get("success"):
            ids = [(a.get("id"), a.get("name")) for a in (c.get("result") or [])]
            fuera.append(f"- cuentas a las que llega el token: {len(ids)}")
            for i, n in ids:
                marca = "  ← **es la nuestra**" if i == cuenta else ""
                fuera.append(f"    - {n} · `{(i or '')[:6]}…{(i or '')[-4:]}`{marca}")
            if ids and cuenta not in [i for i, _ in ids]:
                fuera += ["", "**Ahí está el fallo**: el Account ID guardado no es "
                          "ninguna de las cuentas del token. Hay que cambiar el "
                          "secreto `CF_ACCOUNT_ID` por el de arriba."]
        else:
            fuera.append(f"- no deja listar cuentas: {str(c.get('errors'))[:200]}")
    except Exception as e:  # noqa: BLE001
        fuera.append(f"- no se pudo listar cuentas: {type(e).__name__}: {e}")

    if valido:
        fuera += ["", "El token vale pero la llamada a Workers AI da 401, así que "
                  "lo que falta es el **permiso**: el token tiene que llevar "
                  "`Account` → `Workers AI` → `Read`. Se arregla editando el "
                  "token en https://dash.cloudflare.com/profile/api-tokens o "
                  "creando uno nuevo con la plantilla **Workers AI**."]
    elif valido is False:
        fuera += ["", "El token no es válido: lo más probable es que se copiara "
                  "incompleto. Hay que crear uno nuevo y pegarlo entero."]
    return fuera + [""]


def main():
    CARPETA.mkdir(exist_ok=True)
    ahora = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    lineas = [f"# Prueba de Cloudflare · {ahora} UTC", ""]

    if not cloudflare.hay():
        d = cloudflare.diagnostico()
        # Cuál de los dos falta, que es lo único que hace falta saber. Nunca
        # el valor: esto queda escrito en el repositorio.
        lineas += ["**Faltan credenciales.** Esto es lo que se ve:", "",
                   "| secreto | ¿está? | de dónde | longitud |",
                   "|---|---|---|---|"]
        for que, clave in (("Account ID", "cuenta"), ("API token", "ficha")):
            lineas.append(
                f"| {que} | {'sí' if d[clave] else '**NO**'} | "
                f"`{d[clave + '_en'] or '—'}` | {d[clave + '_largo'] or '—'} |")
        lineas += [
            "",
            "Los nombres buenos son `CF_ACCOUNT_ID` y `CF_API_TOKEN`, pero "
            "también valen las variantes: "
            + ", ".join(f"`{n}`" for n in
                        cloudflare.NOMBRES_CUENTA[1:] + cloudflare.NOMBRES_FICHA[1:])
            + ".",
            "",
            "Si uno pone «NO», ese secreto no existe o está escrito con otro "
            "nombre. Se arregla en Settings → Secrets and variables → Actions.",
            "",
            "Como referencia: el Account ID son 32 caracteres; el token, unos 40.",
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

    if not buenas:
        lineas += interrogar()

    lineas += ["---", "",
               f"**{buenas} de {len(ESCENAS)} pasaron el revisor.**", "",
               "Si las fotos son Allie, Cloudflare puede sustituir a Hugging Face: "
               "unas noventa fotos al día en vez de ninguna.", ""]
    (CARPETA / "informe.md").write_text("\n".join(lineas), encoding="utf-8")
    print("\n".join(lineas), flush=True)


if __name__ == "__main__":
    # Si esto revienta por un sitio imprevisto, el informe tiene que contarlo
    # igual: un trabajo en rojo sin nada escrito no se puede diagnosticar.
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        CARPETA.mkdir(exist_ok=True)
        roto = ("\n\n## Reventó por un sitio imprevisto\n\n```\n"
                + traceback.format_exc()[-3000:] + "\n```\n")
        f = CARPETA / "informe.md"
        f.write_text((f.read_text(encoding="utf-8") if f.exists() else "") + roto,
                     encoding="utf-8")
        print(roto, flush=True)
        raise
