"""Cliente de Instagram a través de la API Graph de Facebook.

Esta es la vía que SÍ deja leer los comentarios de otras personas sin pasar por
la revisión de la app (acceso estándar), porque la cuenta de Instagram está
vinculada a una página de Facebook.

Documentación:
- https://developers.facebook.com/docs/instagram-platform/instagram-graph-api
- Comentarios: .../comment-moderation
- Mensajes:    .../instagram-api-with-facebook-login/messaging-api

Host: graph.facebook.com
Permisos: instagram_basic, instagram_manage_comments, instagram_manage_messages,
          pages_show_list, pages_read_engagement, business_management
"""
import json as _json
import os
from datetime import datetime, timezone

import requests

VERSION = os.environ.get("META_API_VERSION", "v26.0")
BASE = f"https://graph.facebook.com/{VERSION}"


class IGError(Exception):
    pass


def ahora():
    return datetime.now(timezone.utc)


def parse_fecha(ts):
    """La API devuelve '2026-10-01T18:30:00+0000'."""
    if not ts:
        return None
    for f in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(ts, f)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pedir(method, url, params):
    try:
        if method == "GET":
            r = requests.get(url, params=params, timeout=60)
        else:
            r = requests.post(url, data=params, timeout=60)
    except requests.RequestException as e:
        raise IGError(f"No se pudo conectar con Meta: {e}")
    try:
        data = r.json()
    except ValueError:
        raise IGError(f"Respuesta no válida de Meta (HTTP {r.status_code})")
    if isinstance(data, dict) and "error" in data:
        e = data["error"]
        raise IGError(f"{e.get('error_user_msg') or e.get('message')} (código {e.get('code')})")
    return data


# ===================================================================== tokens
def token_largo(token, app_id, app_secret):
    """Cambia un token corto por uno de 60 días."""
    d = _pedir("GET", f"{BASE}/oauth/access_token", {
        "grant_type": "fb_exchange_token", "client_id": app_id,
        "client_secret": app_secret, "fb_exchange_token": token})
    return d.get("access_token")


def token_de_pagina(token_usuario):
    """Devuelve (token_de_pagina, id_pagina, id_instagram, nombre_pagina).

    El token de página obtenido a partir de un token de usuario de 60 días
    no caduca mientras no se cambie la contraseña ni se revoquen los permisos.
    """
    d = _pedir("GET", f"{BASE}/me/accounts", {
        "access_token": token_usuario,
        "fields": "name,access_token,instagram_business_account"})
    for pag in d.get("data", []):
        ig = (pag.get("instagram_business_account") or {}).get("id")
        if ig:
            return pag.get("access_token"), pag.get("id"), ig, pag.get("name")
    raise IGError("Ninguna de tus páginas de Facebook tiene una cuenta de Instagram vinculada.")


# ================================================================== Instagram
class Instagram:
    def __init__(self, token=None, ig_id=None, page_id=None):
        self.token = token or os.environ.get("FB_TOKEN", "")
        if not self.token:
            raise IGError("Falta el secreto FB_TOKEN en GitHub.")
        self.base = BASE
        self._yo = str(ig_id) if ig_id else os.environ.get("IG_USER_ID", "") or None
        self._pagina = str(page_id) if page_id else os.environ.get("FB_PAGE_ID", "") or None
        self.mi_usuario = None

    # ------------------------------------------------------------- básico
    def _req(self, method, path, **params):
        url = path if path.startswith("http") else f"{self.base}/{str(path).lstrip('/')}"
        params["access_token"] = self.token
        return _pedir(method, url, params)

    def _lista(self, path, maximo=200, **params):
        data = self._req("GET", path, **params)
        items = list(data.get("data", []))
        while len(items) < maximo and data.get("paging", {}).get("next"):
            data = self._req("GET", data["paging"]["next"])
            items.extend(data.get("data", []))
        return items[:maximo]

    # ----------------------------------------------------------- descubrir
    def descubrir(self):
        """Encuentra la página y la cuenta de Instagram a partir del token."""
        d = self._req("GET", "me/accounts", fields="name,instagram_business_account")
        for pag in d.get("data", []):
            ig = (pag.get("instagram_business_account") or {}).get("id")
            if ig:
                self._pagina, self._yo = str(pag.get("id")), str(ig)
                return self._pagina, self._yo
        raise IGError("No encuentro ninguna página con cuenta de Instagram vinculada.")

    @property
    def yo(self):
        if not self._yo:
            self.descubrir()
        return self._yo

    @property
    def pagina(self):
        if not self._pagina:
            self.descubrir()
        return self._pagina

    # ------------------------------------------------------------- cuenta
    def cuenta(self):
        d = self._req("GET", self.yo, fields="id,username,followers_count,media_count")
        self.mi_usuario = d.get("username")
        return d

    # --------------------------------------------------------- comentarios
    def publicaciones(self, maximo=25):
        return self._lista(f"{self.yo}/media", maximo, limit=25,
                           fields="id,caption,permalink,timestamp,comments_count")

    def comentarios(self, media_id, maximo=100):
        campos = "id,text,timestamp,username,from,replies{id,username,from,text}"
        try:
            return self._lista(f"{media_id}/comments", maximo, limit=50, fields=campos)
        except IGError:
            return self._lista(f"{media_id}/comments", maximo, limit=50,
                               fields="id,text,timestamp,username,replies{id,username,text}")

    def responder_comentario(self, comment_id, texto):
        return self._req("POST", f"{comment_id}/replies", message=texto[:2200])["id"]

    # ------------------------------------------------------------ mensajes
    def conversaciones(self, maximo=50):
        # Meta responde "reduce the amount of data" si se piden demasiadas de
        # golpe, así que se va bajando el tamaño de página hasta que acepte.
        ultimo = None
        for tam in (25, 10, 5, 2):
            try:
                return self._lista(f"{self.pagina}/conversations", maximo,
                                   platform="instagram", fields="id,updated_time", limit=tam)
            except IGError as e:
                ultimo = e
                if "reduce the amount of data" not in str(e).lower():
                    raise
        raise ultimo

    def mensajes(self, conversacion_id, maximo=20):
        campos = "messages.limit(%d){id,created_time,from,to,message}" % maximo
        try:
            d = self._req("GET", conversacion_id, fields=campos)
            msgs = (d.get("messages") or {}).get("data", [])
            if msgs and "created_time" in msgs[0]:
                return msgs
        except IGError:
            pass
        d = self._req("GET", conversacion_id, fields="messages")
        out = []
        for m in (d.get("messages") or {}).get("data", [])[:maximo]:
            try:
                out.append(self._req("GET", m["id"], fields="id,created_time,from,to,message"))
            except IGError:
                continue
        return out

    def enviar_mensaje(self, igsid, texto):
        return self._req("POST", f"{self.pagina}/messages",
                         recipient=_json.dumps({"id": str(igsid)}),
                         messaging_type="RESPONSE",
                         message=_json.dumps({"text": texto[:900]}))
