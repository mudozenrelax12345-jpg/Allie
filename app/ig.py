"""Cliente de la API de Instagram (API con inicio de sesión de Instagram).

Documentación:
- Comentarios:  https://developers.facebook.com/docs/instagram-platform/comment-moderation
- Conversaciones: https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/conversations-api
Host: graph.instagram.com
Permisos: instagram_business_basic, instagram_business_manage_comments, instagram_business_manage_messages
"""
import os
from datetime import datetime, timezone

import requests

VERSION = os.environ.get("INSTAGRAM_API_VERSION", "v25.0")


class IGError(Exception):
    pass


def ahora():
    return datetime.now(timezone.utc)


def parse_fecha(ts):
    """Instagram devuelve '2026-10-01T18:30:00+0000'."""
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


class Instagram:
    def __init__(self, token=None):
        self.token = token or os.environ.get("INSTAGRAM_TOKEN", "")
        if not self.token:
            raise IGError("Falta el secreto INSTAGRAM_TOKEN en GitHub.")
        self.base = f"https://graph.instagram.com/{VERSION}"
        self._yo = None

    # ------------------------------------------------------------- básico
    def _req(self, method, path, **params):
        url = path if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"
        params["access_token"] = self.token
        try:
            if method == "GET":
                r = requests.get(url, params=params, timeout=60)
            else:
                r = requests.post(url, data=params, timeout=60)
        except requests.RequestException as e:
            raise IGError(f"No se pudo conectar con Instagram: {e}")
        try:
            data = r.json()
        except ValueError:
            raise IGError(f"Respuesta no válida de Instagram (HTTP {r.status_code})")
        if isinstance(data, dict) and "error" in data:
            e = data["error"]
            raise IGError(f"{e.get('error_user_msg') or e.get('message')} (código {e.get('code')})")
        return data

    def _lista(self, path, maximo=200, **params):
        data = self._req("GET", path, **params)
        items = list(data.get("data", []))
        while len(items) < maximo and data.get("paging", {}).get("next"):
            data = self._req("GET", data["paging"]["next"])
            items.extend(data.get("data", []))
        return items[:maximo]

    # ------------------------------------------------------------- cuenta
    def cuenta(self):
        d = self._req("GET", "me", fields="user_id,username,account_type,followers_count")
        self._yo = str(d.get("user_id") or d.get("id") or "")
        return d

    @property
    def yo(self):
        if self._yo is None:
            self.cuenta()
        return self._yo

    def refrescar_token(self):
        d = self._req("GET", "https://graph.instagram.com/refresh_access_token",
                      grant_type="ig_refresh_token")
        return d.get("access_token"), d.get("expires_in")

    # --------------------------------------------------------- comentarios
    def publicaciones(self, maximo=25):
        return self._lista("me/media", maximo, limit=25,
                           fields="id,caption,permalink,timestamp,comments_count")

    def comentarios(self, media_id, maximo=100):
        campos = "id,text,timestamp,username,from,parent_id,replies{id,from,username,text}"
        try:
            return self._lista(f"{media_id}/comments", maximo, limit=50, fields=campos)
        except IGError:
            # Si 'from' no está disponible (permiso), se pide una versión reducida
            return self._lista(f"{media_id}/comments", maximo, limit=50,
                               fields="id,text,timestamp,username,parent_id,replies{id,username,text}")

    def responder_comentario(self, comment_id, texto):
        return self._req("POST", f"{comment_id}/replies", message=texto[:2200])["id"]

    # -------------------------------------------------------------- mensajes
    def conversaciones(self, maximo=50):
        return self._lista("me/conversations", maximo, platform="instagram",
                           fields="id,updated_time", limit=50)

    def mensajes(self, conversacion_id, maximo=20):
        """Devuelve los mensajes más recientes (Instagram solo da los últimos 20)."""
        campos = "messages.limit(%d){id,created_time,from,to,message}" % maximo
        try:
            d = self._req("GET", conversacion_id, fields=campos)
            msgs = (d.get("messages") or {}).get("data", [])
            if msgs and "created_time" in msgs[0]:
                return msgs
        except IGError:
            msgs = []
        # Alternativa: pedir los ids y luego el detalle de cada uno
        d = self._req("GET", conversacion_id, fields="messages")
        out = []
        for m in (d.get("messages") or {}).get("data", [])[:maximo]:
            try:
                out.append(self._req("GET", m["id"], fields="id,created_time,from,to,message"))
            except IGError:
                continue
        return out

    def enviar_mensaje(self, igsid, texto):
        import json
        return self._req("POST", f"{self.yo}/messages",
                         recipient=json.dumps({"id": str(igsid)}),
                         message=json.dumps({"text": texto[:900]}))
