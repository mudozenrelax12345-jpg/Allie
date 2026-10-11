"""Comprueba que, sin cuota, el generador para en seco y no insiste.

Esto se ha roto dos veces, y las dos de forma silenciosa: el trabajo tarda
siete minutos en vez de uno, y por fuera parece simplemente que «falló».

La primera vez el programa reintentaba seis veces contra un error de cuota
que no se arregla esperando. La segunda la provoqué yo al poner varios
espacios: la condición para parar era que TODOS dijeran que no había cuota, y
con uno contestando «sin cuota» y otro dando un error propio, dejaba de
cumplirse. Volvió a hacer seis tandas.

La regla correcta, y es lo que se prueba aquí: basta con que UNO lo diga. La
cuota de ZeroGPU es una por cuenta y la comparten todos los espacios, así que
si falta en uno falta en todos.

No llama a Hugging Face: sustituye el generador por uno de mentira y cuenta
las llamadas.
"""
import sys
import types
from pathlib import Path

# kontext() comprueba que gradio_client esté instalado y, si no, se va sin
# llegar al generador. Aquí no hace falta de verdad —el generador se
# sustituye por uno de mentira—, así que se pone uno vacío para que la
# prueba funcione en cualquier sitio, incluido un portátil sin la librería.
if "gradio_client" not in sys.modules:
    falso = types.ModuleType("gradio_client")
    falso.Client = object
    falso.handle_file = lambda x: x
    sys.modules["gradio_client"] = falso

sys.path.insert(0, str(Path(__file__).resolve().parent))
import espacio as espacio_mod  # noqa: E402
import reel  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que
          + (f"  ·  {detalle}" if not bien and detalle else ""), flush=True)
    if not bien:
        fallos.append(que)


def con_generador(falso, espacios, prueba):
    """Ejecuta `prueba` con el generador y la lista de espacios sustituidos."""
    orig_gen, orig_esp, orig_ref = (espacio_mod.generar, list(reel.ESPACIOS),
                                    reel.referencia_vertical)
    espacio_mod.generar = falso
    reel.ESPACIOS[:] = espacios
    reel.referencia_vertical = lambda url: Path("/dev/null")
    try:
        return prueba()
    finally:
        espacio_mod.generar = orig_gen
        reel.ESPACIOS[:] = orig_esp
        reel.referencia_vertical = orig_ref


SIN_CUOTA = "AppError: You have exceeded your ZeroGPU runs limit."


def main():
    p = {"referencia_url": "x"}

    # 1 · Un solo espacio y sin cuota: tiene que levantar SinCuota.
    llamadas = []

    def solo_cuota(esp, ficha, img, orden, pasos):
        llamadas.append(esp)
        return None, 0, [f"{esp}: {SIN_CUOTA}"]

    def intentar():
        try:
            reel.kontext("una escena", p)
            return "devolvió sin avisar"
        except reel.SinCuota:
            return "SinCuota"
        except Exception as e:  # noqa: BLE001
            return f"{type(e).__name__}: {e}"

    r = con_generador(solo_cuota, ["uno"], intentar)
    comprobar("sin cuota en el único espacio levanta SinCuota", r == "SinCuota", r)

    # 2 · El caso que se rompió: uno dice «sin cuota» y otro da un error suyo.
    # Antes, al no decirlo TODOS, no se levantaba SinCuota y quien llamaba
    # repetía la tanda seis veces.
    llamadas.clear()

    def mezcla(esp, ficha, img, orden, pasos):
        llamadas.append(esp)
        if esp == "uno":
            return None, 0, [f"{esp}: {SIN_CUOTA}"]
        return None, 0, [f"{esp}: AppError: algo raro suyo"]

    r = con_generador(mezcla, ["uno", "dos", "tres"], intentar)
    comprobar("con uno sin cuota y otro con error propio, también para",
              r == "SinCuota", r)
    comprobar("y no sigue probando los demás espacios",
              set(llamadas) == {"uno"}, f"probó {llamadas}")

    # 3 · Un error que NO es de cuota no debe levantar SinCuota: ahí sí tiene
    # sentido reintentar, porque puede ser pasajero.
    def otro_error(esp, ficha, img, orden, pasos):
        return None, 0, [f"{esp}: ConnectionError: se cayó"]

    r = con_generador(otro_error, ["uno", "dos"], intentar)
    comprobar("un error que no es de cuota no levanta SinCuota",
              r == "devolvió sin avisar", r)

    # 4 · Si uno funciona, se usa y se apunta cuánto costó.
    reel.GASTO.clear()

    def bueno(esp, ficha, img, orden, pasos):
        from PIL import Image
        f = Path("/tmp/prueba-cuota.png")
        Image.new("RGB", (64, 64), "white").save(f)
        return f, 7.5, "/infer"

    def generar():
        datos, _ = reel.kontext("una escena", p)
        return datos

    datos = con_generador(bueno, ["uno"], generar)
    comprobar("si un espacio funciona, devuelve la imagen", bool(datos))
    comprobar("y apunta los segundos que costó",
              len(reel.GASTO) == 1 and reel.GASTO[0]["segundos"] == 7.5,
              f"{reel.GASTO}")

    # 5 · Sin cuota por el token NO es sin cuota a secas: la del token va por
    # cuenta y la anónima por dirección IP, y cada ejecución de GitHub estrena
    # máquina. Antes se cortaba en cuanto lo decía la primera vía, así que la
    # segunda oportunidad que busca este diseño no se usaba nunca. Pasó hoy:
    # el día entero sin una sola foto y sin gastar un segundo de GPU.
    import os
    reel.GASTO.clear()
    vias = []

    def token_sin_cuota(esp, ficha, img, orden, pasos):
        vias.append("con cuenta" if ficha else "sin cuenta")
        if ficha:
            return None, 0, [f"{esp}: {SIN_CUOTA}"]
        from PIL import Image
        f = Path("/tmp/prueba-cuota-anon.png")
        Image.new("RGB", (64, 64), "white").save(f)
        return f, 9.1, "/infer"

    antes = os.environ.get("HF_TOKEN")
    os.environ["HF_TOKEN"] = "ficha-de-mentira"
    try:
        datos = con_generador(token_sin_cuota, ["uno"], generar)
    finally:
        if antes is None:
            os.environ.pop("HF_TOKEN", None)
        else:
            os.environ["HF_TOKEN"] = antes
    comprobar("sin cuota con el token, aún prueba sin cuenta",
              vias == ["con cuenta", "sin cuenta"], f"probó {vias}")
    comprobar("y si la vía anónima tiene cuota, sale la foto", bool(datos))

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal:", flush=True)
        for f in fallos:
            print(f"  · {f}", flush=True)
        sys.exit(1)
    print("\nel corte por falta de cuota funciona", flush=True)


if __name__ == "__main__":
    main()
