"""Comprueba que el vídeo sale marcado como generado con IA, y sin estropearse.

La declaración del pie la leen las personas; esta la leen las máquinas, y
es la que hace que Instagram ponga su propia etiqueta. Pero un marcado que
recodifica o corta el vídeo sería cambiar una formalidad por un fallo de
verdad, así que se comprueban las dos cosas: que la etiqueta está y que el
vídeo sigue entero.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import marca  # noqa: E402

fallos = []


def comprobar(que, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + que + (f"  ·  {detalle}" if not bien and detalle else ""),
          flush=True)
    if not bien:
        fallos.append(que)


def duracion(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(ruta)],
                       capture_output=True, text=True, timeout=60)
    try:
        return round(float(r.stdout.strip()), 1)
    except Exception:  # noqa: BLE001
        return None


def main():
    tmp = Path(tempfile.mkdtemp(prefix="marca-"))
    v = tmp / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=320x400:rate=25:duration=3",
                    "-pix_fmt", "yuv420p", str(v)], check=True, timeout=120)
    antes_bytes, antes_dur = v.stat().st_size, duracion(v)

    ok, detalle = marca.marcar(v)
    comprobar("el vídeo se marca", ok, detalle)

    tags = marca.leer(v)
    comprobar("lleva el DigitalSourceType del IPTC",
              "trainedAlgorithmicMedia" in tags, tags[:200])
    comprobar("y un aviso legible en el comentario",
              "generada con inteligencia artificial" in tags
              or "generado con inteligencia artificial" in tags, tags[:200])

    comprobar("el vídeo no se ha recodificado",
              abs(v.stat().st_size - antes_bytes) < antes_bytes * 0.1,
              f"{antes_bytes} → {v.stat().st_size}")
    comprobar("y dura lo mismo", duracion(v) == antes_dur,
              f"{antes_dur} → {duracion(v)}")

    # Un fichero que no existe no debe reventar el reel entero.
    ok2, _ = marca.marcar(tmp / "no-existe.mp4")
    comprobar("un fichero que falta no revienta nada", ok2 is False)

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    if fallos:
        print(f"\n{len(fallos)} comprobaciones mal", flush=True)
        sys.exit(1)
    print("\nel vídeo sale marcado y entero", flush=True)


if __name__ == "__main__":
    main()
