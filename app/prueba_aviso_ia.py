"""Comprueba que a nadie se le contesta en privado sin decirle que es un bot.

En un comentario público el contexto lo da todo: la cuenta se llama
@allie.the.ai y la biografía dice que es un personaje de IA. En un privado no
hay nada de eso, y quien escribe asume que le contesta una persona.

Lo que se comprueba:
  · la primera respuesta a cada persona lleva el aviso, y va DELANTE,
  · la segunda ya no lo repite (sería pesado y no aporta),
  · dos personas distintas reciben cada una el suyo,
  · el identificador que se guarda para saberlo NO identifica a nadie,
  · y lo que se contesta queda apuntado, cifrado y no legible en claro.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import main as bot  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que + (f"  ·  {detalle}" if not bien and detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


SECRETO = "token-de-mentira-para-la-prueba"


def primera_respuesta(estado, igsid, respuesta, p=None):
    """Lo mismo que hace responder_mensajes al enviar, aislado."""
    huella = bot._quien(SECRETO, igsid)
    avisados = set(estado.get("avisados_ia") or [])
    if huella not in avisados:
        respuesta = ((p or {}).get("aviso_ia") or bot.AVISO_IA_POR_OMISION) + "\n\n" + respuesta
        avisados.add(huella)
        estado["avisados_ia"] = list(avisados)
    return respuesta


def main():
    estado = {}
    r1 = primera_respuesta(estado, "ig-persona-1", "¡Gracias! Es de Zara.")
    comprobar("la primera respuesta avisa de que es un bot",
              "creado con IA" in r1, r1[:70])
    comprobar("y el aviso va DELANTE de la respuesta",
              r1.startswith("Por cierto, te contesta"), r1[:40])

    r2 = primera_respuesta(estado, "ig-persona-1", "Sí, en Malasaña.")
    comprobar("la segunda vez no lo repite", "creado con IA" not in r2, r2[:70])

    r3 = primera_respuesta(estado, "ig-persona-2", "¡Hola!")
    comprobar("otra persona sí recibe el suyo", "creado con IA" in r3, r3[:70])

    # El identificador guardado no puede delatar a nadie: el repositorio es
    # público y ahí quedaría escrito a quién le habla Allie.
    guardados = estado["avisados_ia"]
    comprobar("se guardan dos huellas, una por persona", len(guardados) == 2, str(guardados))
    comprobar("y ninguna contiene el identificador de Instagram",
              not any("persona" in g for g in guardados), str(guardados))
    comprobar("la huella depende del secreto, no es un hash público",
              bot._quien("otro-secreto", "ig-persona-1") != bot._quien(SECRETO, "ig-persona-1"))

    # El diario: cifrado, y que de verdad no se lea en claro.
    tmp = Path(tempfile.mkdtemp(prefix="diario-"))
    antes = bot.DIARIO
    bot.DIARIO = tmp / "privados.enc"
    try:
        bot.apuntar_privado(SECRETO, {"cuando": "2026-10-16T19:00", "de": "mariagarcia",
                                      "recibido": "¿eres real?", "contestado": "soy un personaje de IA"})
        bot.apuntar_privado(SECRETO, {"cuando": "2026-10-16T19:05", "de": "otra",
                                      "recibido": "qué guapa", "contestado": "¡gracias!"})
        crudo = bot.DIARIO.read_bytes()
        comprobar("el diario no se lee en claro",
                  b"mariagarcia" not in crudo and b"eres real" not in crudo,
                  crudo[:60].decode("utf-8", "replace"))
        leido = json.loads(bot._fernet(SECRETO).decrypt(crudo).decode())
        comprobar("pero con la llave sí, y están los dos", len(leido) == 2, str(leido)[:90])
        comprobar("y guarda lo que se contestó, no solo que se contestó",
                  leido[0]["contestado"] == "soy un personaje de IA", str(leido[0]))
        comprobar("con otra llave no se abre",
                  _no_se_abre(bot, crudo))
    finally:
        bot.DIARIO = antes
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal", flush=True)
        sys.exit(1)
    print("\nnadie recibe respuesta privada sin saber que habla con un bot", flush=True)


def _no_se_abre(bot, crudo):
    try:
        bot._fernet("llave-equivocada").decrypt(crudo)
        return False
    except Exception:  # noqa: BLE001
        return True


if __name__ == "__main__":
    main()
