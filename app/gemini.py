"""Textos con la API de Gemini (el nivel gratuito cubre texto)."""
import json
import os
import re

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
MODELO = os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.5-flash")


class GeminiError(Exception):
    pass


def _clave():
    k = os.environ.get("GEMINI_API_KEY", "")
    if not k:
        raise GeminiError("Falta el secreto GEMINI_API_KEY en GitHub.")
    return k


def _post(url, body):
    try:
        r = requests.post(url, headers={"x-goog-api-key": _clave(), "Content-Type": "application/json"},
                          json=body, timeout=120)
    except requests.RequestException as e:
        raise GeminiError(f"No se pudo conectar con Gemini: {e}")
    if r.status_code == 404:
        return None
    try:
        data = r.json()
    except ValueError:
        raise GeminiError(f"Respuesta no válida de Gemini (HTTP {r.status_code})")
    if r.status_code >= 400 or "error" in data:
        raise GeminiError(f"Gemini: {data.get('error', {}).get('message', r.text[:200])}")
    return data


def _textos(nodo, out):
    if isinstance(nodo, dict):
        if nodo.get("type") == "thought" or nodo.get("thought") is True:
            return
        if isinstance(nodo.get("text"), str) and nodo.get("type", "text") == "text":
            out.append(nodo["text"])
        for k, v in nodo.items():
            if k not in ("input", "usage", "usageMetadata"):
                _textos(v, out)
    elif isinstance(nodo, list):
        for v in nodo:
            _textos(v, out)


def texto(prompt):
    data = _post(f"{BASE}/interactions", {"model": MODELO, "input": [{"type": "text", "text": prompt}]})
    if data is None:
        data = _post(f"{BASE}/models/{MODELO}:generateContent",
                     {"contents": [{"role": "user", "parts": [{"text": prompt}]}]})
        if data is None:
            raise GeminiError(f"El modelo '{MODELO}' no existe. Cámbialo en el secreto GEMINI_TEXT_MODEL.")
    out = []
    if isinstance(data.get("steps"), list):
        nodos = [s for s in data["steps"] if s.get("type") == "model_output"] or data["steps"]
    else:
        nodos = data.get("outputs") or data.get("candidates") or data
    _textos(nodos, out)
    return "\n".join(out).strip()


def json_(prompt):
    t = texto(prompt)
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        raise GeminiError("Gemini no devolvió un JSON válido.")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise GeminiError(f"JSON inválido de Gemini: {e}")
