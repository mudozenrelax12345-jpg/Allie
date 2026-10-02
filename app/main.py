"""Responde automáticamente a los comentarios y mensajes de Instagram.

Se ejecuta en GitHub Actions cada hora:
- Lee los comentarios nuevos de las últimas publicaciones y contesta uno a uno.
- Lee los mensajes directos nuevos y contesta (Instagram solo permite responder
  dentro de las 24 h siguientes al mensaje de la persona).
- Lo que es delicado no se contesta: se abre un aviso en la pestaña Issues.
"""
import base64
import hashlib
import json
import os
import sys
import time
import traceback
from datetime import timedelta
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gemini
from ig import IGError, Instagram, ahora, parse_fecha, token_de_pagina, token_largo

BASE_DIR = Path(__file__).resolve().parent.parent
ESTADO = BASE_DIR / "estado" / "estado.json"
TOKEN_FILE = BASE_DIR / "estado" / "credenciales.json"
PERSONA_FILE = BASE_DIR / "personaje.yml"

APP_ID = os.environ.get("META_APP_ID", "1396445209313937")

MAX_COMENTARIOS = 30          # por ejecución
MAX_MENSAJES = 20
DIAS_PUBLICACIONES = 30       # solo se revisan los comentarios de posts recientes
PAUSA = 1.5                   # segundos entre llamadas a Gemini


def log(msg):
    print(f"· {msg}", flush=True)


# ============================================================ estado y token
def cargar_estado():
    if ESTADO.exists():
        try:
            return json.loads(ESTADO.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"comentarios": [], "mensajes": [], "conversaciones": {}}


def guardar_estado(e):
    e["comentarios"] = e["comentarios"][-3000:]
    e["mensajes"] = e["mensajes"][-3000:]
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def _fernet(secreto):
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"allie:" + secreto.encode()).digest()))


def _origen(secreto):
    return hashlib.sha256(b"origen:" + secreto.encode()).hexdigest()[:16]


def credenciales():
    """Devuelve (token, id_instagram, id_pagina).

    La primera vez cambia el token corto del Explorador por uno de 60 días y, a
    partir de él, saca el token de la página de Facebook, que no caduca. Se
    guarda cifrado en el repositorio para no volver a pedirlo.
    """
    secreto = os.environ.get("FB_TOKEN", "")
    if not secreto:
        raise RuntimeError("Falta el secreto FB_TOKEN en GitHub.")
    if TOKEN_FILE.exists():
        try:
            d = json.loads(TOKEN_FILE.read_text())
            if d.get("origen") == _origen(secreto):
                tok = _fernet(secreto).decrypt(d["token"].encode()).decode()
                return tok, d.get("ig_id"), d.get("page_id")
        except Exception as e:  # noqa: BLE001
            log(f"No se pudieron leer las credenciales guardadas: {e}")

    token = secreto
    app_secret = os.environ.get("META_APP_SECRET", "")
    if app_secret:
        try:
            largo = token_largo(secreto, APP_ID, app_secret)
            if largo:
                token = largo
                log("Token alargado a 60 días.")
        except IGError as e:
            log(f"No pude alargar el token: {e}")
    try:
        pt, page_id, ig_id, nombre = token_de_pagina(token)
    except IGError as e:
        log(f"No pude sacar el token de la página: {e}")
        return token, None, None
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({
        "origen": _origen(secreto), "ig_id": ig_id, "page_id": page_id, "pagina": nombre,
        "token": _fernet(secreto).encrypt(pt.encode()).decode(),
        "creado": ahora().isoformat()}, ensure_ascii=False, indent=1))
    log(f"Token permanente de la página «{nombre}» guardado.")
    return pt, ig_id, page_id


# ============================================================ GitHub (avisos)
class GitHub:
    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN", "")
        self.repo = os.environ.get("GITHUB_REPOSITORY", "")

    @property
    def activo(self):
        return bool(self.token and self.repo)

    def _req(self, method, path, **kw):
        r = requests.request(method, f"https://api.github.com/repos/{self.repo}{path}", timeout=60,
                             headers={"Authorization": f"Bearer {self.token}",
                                      "Accept": "application/vnd.github+json",
                                      "X-GitHub-Api-Version": "2022-11-28"}, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub {method} {path}: {r.status_code} {r.text[:200]}")
        return r.json() if r.content else None

    def issue(self, titulo, cuerpo, etiqueta="revisar"):
        if not self.activo:
            log(f"[aviso] {titulo}\n{cuerpo}")
            return
        try:
            existentes = {e["name"] for e in self._req("GET", "/labels", params={"per_page": 100})}
            if etiqueta not in existentes:
                self._req("POST", "/labels", json={"name": etiqueta, "color": "fbca04",
                                                   "description": "Necesita tu atención"})
            self._req("POST", "/issues", json={"title": titulo, "body": cuerpo, "labels": [etiqueta]})
        except RuntimeError as e:
            log(f"No se pudo crear el aviso: {e}")


# ============================================================ personaje
BASE_PERSONA = {
    "nombre": "Allie",
    "usuario": "@allie.the.ai",
    "personalidad": "Cercana, divertida y positiva. Habla de tú, frases cortas, algún emoji.",
    "sobre_ella": "",
    "decir_que_es_ia": True,
    "temas_a_evitar": "política, religión, salud, dinero",
    "firma": "",
}


def persona():
    if not PERSONA_FILE.exists():
        return dict(BASE_PERSONA)
    try:
        d = yaml.safe_load(PERSONA_FILE.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise RuntimeError(f"personaje.yml tiene un error de formato: {e}")
    return {**BASE_PERSONA, **{k: v for k, v in d.items() if v not in (None, "")}}


REGLAS = """
Decide qué hacer con este {tipo} que ha recibido {nombre} ({usuario}) en Instagram.

QUIÉN ES {nombre}
{personalidad}
{sobre_ella}

RESPONDE (accion "responder") cuando sea un {tipo} normal: piropos, emojis, preguntas
sobre la foto, la ropa, el sitio, sus mascotas, su día a día, o conversación amable.

AVISA A LA DUEÑA (accion "avisar", sin escribir respuesta) cuando haya:
- propuestas de colaboración, marcas, publicidad, ventas, dinero o cualquier negocio;
- insultos, acoso, amenazas, contenido sexual o insinuaciones subidas de tono;
- señales de que quien escribe es menor de edad;
- peticiones de datos personales, teléfono, dirección, otras redes o quedar en persona;
- temas delicados ({temas_a_evitar}), consejos médicos, legales o financieros;
- alguien que parece estar pasándolo mal o pide ayuda de verdad;
- cualquier cosa que no se pueda responder con seguridad o que tenga trampa.

IGNORA (accion "ignorar") solo el spam evidente, los bots y los enlaces promocionales.

CÓMO ESCRIBIR LA RESPUESTA
- En el MISMO IDIOMA en el que te han escrito (si escriben en inglés, responde en inglés).
- Con la voz de {nombre}: {personalidad}
- Muy breve: {largo}. Natural, nada de sonar a robot ni repetir la pregunta.
- Puedes devolver una pregunta corta para dar conversación, pero no siempre.
- Nada de hashtags, enlaces, datos de contacto ni promesas de nada.
- Si preguntan si es real o si es una IA: {honestidad}
{firma}

{tipo_mayus} RECIBIDO
Persona: {autor}
Texto: {texto}
{contexto}

Devuelve SOLO un JSON:
{{"accion": "responder|avisar|ignorar", "respuesta": "texto de la respuesta o cadena vacía", "motivo": "por qué, en español, muy breve"}}
"""


def decidir(p, tipo, autor, texto, contexto=""):
    honestidad = ("responde con naturalidad y honestidad que es un personaje virtual creado con IA"
                  if p.get("decir_que_es_ia", True) else
                  "contesta con humor y sin entrar en el tema, pero NUNCA afirmes ser una persona real")
    prompt = REGLAS.format(
        tipo=tipo, tipo_mayus=tipo.upper(), nombre=p["nombre"], usuario=p["usuario"],
        personalidad=p["personalidad"], sobre_ella=p.get("sobre_ella", ""),
        temas_a_evitar=p.get("temas_a_evitar", ""),
        largo="1 línea, máximo 2" if tipo == "comentario" else "2 líneas, máximo 3",
        honestidad=honestidad,
        firma=f"- Termina siempre con: {p['firma']}" if p.get("firma") else "",
        autor=autor or "desconocido", texto=texto or "(sin texto)", contexto=contexto)
    r = gemini.json_(prompt)
    accion = str(r.get("accion", "avisar")).lower().strip()
    if accion not in ("responder", "avisar", "ignorar"):
        accion = "avisar"
    respuesta = (r.get("respuesta") or "").strip()
    if accion == "responder" and not respuesta:
        accion = "avisar"
    return accion, respuesta, (r.get("motivo") or "").strip()


# ============================================================ comentarios
MI_USUARIO = ""      # se rellena al arrancar; sirve para reconocer lo escrito por Allie


def mio(obj, yo):
    f = obj.get("from") or {}
    if f.get("id") and str(f["id"]) == str(yo):
        return True
    usuario = (obj.get("username") or f.get("username") or "").lower()
    return bool(MI_USUARIO) and usuario == MI_USUARIO


def ya_respondido(c, yo):
    for r in (c.get("replies") or {}).get("data", []):
        if mio(r, yo):
            return True
    return False


def responder_comentarios(ig, gh, p, estado):
    hechos = set(estado["comentarios"])
    limite = ahora() - timedelta(days=DIAS_PUBLICACIONES)
    nuevos = respondidos = avisos = 0
    for media in ig.publicaciones(25):
        fecha = parse_fecha(media.get("timestamp"))
        if fecha and fecha < limite:
            continue
        if not media.get("comments_count"):
            continue
        try:
            comentarios = ig.comentarios(media["id"])
        except IGError as e:
            log(f"No pude leer los comentarios de {media['id']}: {e}")
            continue
        for c in comentarios:
            if respondidos + avisos >= MAX_COMENTARIOS:
                log("Límite de comentarios por ejecución alcanzado; sigo en la próxima.")
                estado["comentarios"] = list(hechos)
                return nuevos, respondidos, avisos
            cid = str(c.get("id"))
            if not cid or cid in hechos or mio(c, ig.yo) or ya_respondido(c, ig.yo):
                continue
            autor = c.get("username") or (c.get("from") or {}).get("username") or "alguien"
            if autor == (estado.get("mi_usuario") or ""):
                continue
            nuevos += 1
            contexto = f"Publicación: {(media.get('caption') or '')[:200]}"
            try:
                accion, respuesta, motivo = decidir(p, "comentario", autor, c.get("text"), contexto)
            except gemini.GeminiError as e:
                log(f"Gemini falló con el comentario {cid}: {e}")
                continue
            time.sleep(PAUSA)
            if accion == "responder":
                try:
                    ig.responder_comentario(cid, respuesta)
                    respondidos += 1
                    log(f"Respondido a @{autor}: {respuesta[:60]}")
                except IGError as e:
                    log(f"No pude responder al comentario {cid}: {e}")
                    continue
            elif accion == "avisar":
                avisos += 1
                gh.issue(f"💬 Comentario para revisar · @{autor}",
                         f"**@{autor}** ha comentado:\n\n> {c.get('text', '')}\n\n"
                         f"**Por qué te aviso:** {motivo}\n\n"
                         f"Publicación: {media.get('permalink', '')}\n\n"
                         f"_No he respondido nada. Contéstale tú desde Instagram si quieres._")
                log(f"Aviso por comentario de @{autor}: {motivo}")
            hechos.add(cid)
    estado["comentarios"] = list(hechos)
    return nuevos, respondidos, avisos


# ============================================================ mensajes
def responder_mensajes(ig, gh, p, estado):
    hechos = set(estado["mensajes"])
    limite24 = ahora() - timedelta(hours=23, minutes=30)
    nuevos = respondidos = avisos = 0
    try:
        conversaciones = ig.conversaciones(50)
    except IGError as e:
        log(f"No pude leer las conversaciones: {e}")
        return 0, 0, 0
    for conv in conversaciones:
        if respondidos + avisos >= MAX_MENSAJES:
            log("Límite de mensajes por ejecución alcanzado; sigo en la próxima.")
            break
        actualizada = parse_fecha(conv.get("updated_time"))
        if actualizada and actualizada < limite24:
            continue
        try:
            mensajes = ig.mensajes(conv["id"])
        except IGError as e:
            log(f"No pude leer la conversación {conv['id']}: {e}")
            continue
        mensajes = sorted([m for m in mensajes if m.get("created_time")],
                          key=lambda m: parse_fecha(m["created_time"]) or ahora())
        if not mensajes:
            continue
        ultimo = mensajes[-1]
        if mio(ultimo, ig.yo):
            continue  # el último mensaje es nuestro: no hay nada que contestar
        mid = str(ultimo.get("id"))
        if not mid or mid in hechos:
            continue
        fecha = parse_fecha(ultimo.get("created_time"))
        if fecha and fecha < limite24:
            hechos.add(mid)
            log("Un mensaje ha pasado de las 24 h: Instagram ya no deja responderlo.")
            continue
        nuevos += 1
        autor = (ultimo.get("from") or {}).get("username") or "alguien"
        igsid = (ultimo.get("from") or {}).get("id")
        historial = "\n".join(
            f"{'Allie' if mio(m, ig.yo) else autor}: {(m.get('message') or '')[:200]}"
            for m in mensajes[-6:-1])
        contexto = f"Mensajes anteriores de esta conversación:\n{historial}" if historial else ""
        try:
            accion, respuesta, motivo = decidir(p, "mensaje", autor, ultimo.get("message"), contexto)
        except gemini.GeminiError as e:
            log(f"Gemini falló con el mensaje {mid}: {e}")
            continue
        time.sleep(PAUSA)
        if accion == "responder" and igsid:
            try:
                ig.enviar_mensaje(igsid, respuesta)
                respondidos += 1
                log(f"Mensaje respondido a @{autor}: {respuesta[:60]}")
            except IGError as e:
                log(f"No pude enviar el mensaje a @{autor}: {e}")
                continue
        elif accion == "avisar":
            avisos += 1
            gh.issue(f"📩 Mensaje para revisar · @{autor}",
                     f"**@{autor}** te ha escrito por privado:\n\n> {ultimo.get('message', '')}\n\n"
                     f"**Por qué te aviso:** {motivo}\n\n"
                     f"_No he respondido nada. Recuerda que Instagram solo deja contestar "
                     f"durante las 24 h siguientes._")
            log(f"Aviso por mensaje de @{autor}: {motivo}")
        hechos.add(mid)
    estado["mensajes"] = list(hechos)
    return nuevos, respondidos, avisos


# ============================================================ acciones
def probar(ig, gh, p):
    lineas = []
    try:
        c = ig.cuenta()
        lineas.append(f"✅ **Instagram**: @{c.get('username')} · {c.get('followers_count')} seguidores")
    except IGError as e:
        lineas.append(f"❌ **Instagram**: {e}")
    # ---- comentarios: qué ve de verdad
    try:
        medias = ig.publicaciones(25)
        limite = ahora() - timedelta(days=DIAS_PUBLICACIONES)
        recientes = [m for m in medias
                     if (parse_fecha(m.get("timestamp")) or ahora()) >= limite]
        total_com = pendientes = 0
        detalle = []
        for m in medias[:10]:
            f = parse_fecha(m.get("timestamp"))
            dentro = f and f >= limite
            n = m.get("comments_count") or 0
            marca = "dentro" if dentro else "FUERA del plazo"
            detalle.append(f"  - {f:%d/%m/%Y} · {n} comentario(s) · {marca}")
            if not dentro:
                continue
            try:
                for com in ig.comentarios(m["id"]):
                    if mio(com, ig.yo):
                        continue
                    total_com += 1
                    if not ya_respondido(com, ig.yo):
                        pendientes += 1
            except IGError as e:
                detalle.append(f"    ⚠️ no pude leer sus comentarios: {e}")
        lineas.append(f"✅ **Comentarios**: {len(medias)} publicaciones, {len(recientes)} dentro de los "
                      f"últimos {DIAS_PUBLICACIONES} días · {total_com} comentarios de otras personas · "
                      f"**{pendientes} sin responder**")
        lineas.append("<details><summary>Tus últimas 10 publicaciones</summary>\n\n"
                      + "\n".join(detalle) + "\n</details>")
        if len(recientes) == 0 and medias:
            lineas.append("ℹ️ Ninguna publicación entra en el plazo: por eso no hay comentarios que "
                          "contestar. Puedo ampliar el plazo si quieres recuperar comentarios antiguos.")
    except IGError as e:
        lineas.append(f"❌ **Comentarios**: {e} (¿falta el permiso de comentarios?)")
    # ---- mensajes
    try:
        convs = ig.conversaciones(50)
        recientes_c = 0
        for conv in convs:
            f = parse_fecha(conv.get("updated_time"))
            if f and f >= ahora() - timedelta(hours=24):
                recientes_c += 1
        lineas.append(f"✅ **Mensajes**: {len(convs)} conversaciones en total · {recientes_c} con "
                      f"actividad en las últimas 24 h (solo esas se pueden contestar, lo impone Instagram)")
        if not convs:
            lineas.append("ℹ️ La API devuelve 0 conversaciones. Si sabes que tienes mensajes, "
                          "activa en la app de Instagram: **Configuración y privacidad → Mensajes "
                          "→ Permitir el acceso a los mensajes** (o «Herramientas conectadas»), "
                          "y vuelve a lanzar esta prueba.")
    except IGError as e:
        lineas.append(f"❌ **Mensajes**: {e} (¿falta el permiso de mensajes?)")
    try:
        r = gemini.json_('Responde solo con este JSON: {"ok": true}')
        lineas.append("✅ **Gemini**: conexión correcta" if r.get("ok") else "⚠️ **Gemini**: respuesta rara")
    except gemini.GeminiError as e:
        lineas.append(f"❌ **Gemini**: {e}")
    lineas.append(f"✅ **Personaje**: {p['nombre']} ({p['usuario']})")
    ok = all(not l.startswith("❌") for l in lineas)
    texto = "\n".join(f"- {l}" if not l.startswith("<") else l for l in lineas)
    gh.issue(f"🔧 Prueba de conexión {'✅' if ok else '❌'}", texto, etiqueta="prueba")
    log(texto)


def diagnostico(ig, gh):
    """Mira en crudo qué devuelve Instagram en los comentarios de las últimas publicaciones."""
    L = []
    try:
        medias = ig.publicaciones(3)
    except IGError as e:
        gh.issue("🔬 Diagnóstico", f"No pude leer las publicaciones: {e}", etiqueta="prueba")
        return
    for m in medias:
        L.append(f"### Publicación del {parse_fecha(m.get('timestamp')):%d/%m/%Y} "
                 f"(comments_count = {m.get('comments_count')})")
        L.append(m.get("permalink", ""))
        for etiqueta, campos in [("con todos los campos", "id,text,timestamp,username,from,parent_id,"
                                                          "replies{id,from,username,text}"),
                                 ("campos mínimos", "id,text,username"),
                                 ("sin indicar campos", None),
                                 ("incluyendo ocultos", "id,text,username,hidden")]:
            try:
                params = {"limit": 50}
                if campos:
                    params["fields"] = campos
                d = ig._req("GET", f"{m['id']}/comments", **params)
                datos = d.get("data", [])
                L.append(f"- **{etiqueta}**: {len(datos)} comentarios")
                for c in datos[:3]:
                    L.append(f"    - `{str(c)[:200]}`")
            except IGError as e:
                L.append(f"- **{etiqueta}**: ❌ {e}")
        L.append("")
    gh.issue("🔬 Diagnóstico de comentarios", "\n".join(L), etiqueta="prueba")
    log("\n".join(L))


def main():
    global MI_USUARIO
    accion = os.environ.get("ACCION", "") or "responder"
    estado = cargar_estado()
    gh = GitHub()
    p = persona()
    token, ig_id, page_id = credenciales()
    ig = Instagram(token, ig_id, page_id)
    try:
        cuenta = ig.cuenta()
        estado["mi_usuario"] = cuenta.get("username")
        MI_USUARIO = (cuenta.get("username") or "").lower()
        if accion == "diagnostico":
            diagnostico(ig, gh)
            guardar_estado(estado)
            return
        if accion == "probar":
            probar(ig, gh, p)
            guardar_estado(estado)
            return
        nc, rc, ac = responder_comentarios(ig, gh, p, estado)
        nm, rm, am = responder_mensajes(ig, gh, p, estado)
        guardar_estado(estado)
        log(f"Comentarios: {nc} nuevos · {rc} respondidos · {ac} para revisar")
        log(f"Mensajes:    {nm} nuevos · {rm} respondidos · {am} para revisar")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        guardar_estado(estado)
        msg = str(e)
        if "código 190" in msg or "FB_TOKEN" in msg:
            gh.issue("⚠️ El token de Meta ha dejado de funcionar",
                     f"Meta ha rechazado el token: `{msg}`\n\nGenera uno nuevo siguiendo el README "
                     "y cámbialo en Settings → Secrets and variables → Actions → FB_TOKEN.")
        else:
            gh.issue("⚠️ Algo ha fallado", f"Error: `{msg}`\n\nSi no sabes qué significa, copia este "
                                            "mensaje y pregúntale a Claude.")
        sys.exit(1)


if __name__ == "__main__":
    main()
