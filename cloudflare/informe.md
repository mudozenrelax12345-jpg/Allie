# Prueba de Cloudflare · 20261013-1525 UTC

## 1 · sitting at a window table in a sunny Madrid café, holding a coffee cup, looking out of the window

- no salió · @cf/black-forest-labs/flux-2-klein-4b: HTTP 401 · {"result":null,"success":false,"errors":[{"code":10000,"message":"Authentication error"}],"messages":[]}
- no salió · @cf/black-forest-labs/flux-2-klein-9b: HTTP 401 · {"result":null,"success":false,"errors":[{"code":10000,"message":"Authentication error"}],"messages":[]}

## 2 · walking along a tree-lined street in autumn, wearing a beige coat, smiling at the camera

- no salió · @cf/black-forest-labs/flux-2-klein-4b: HTTP 401 · {"result":null,"success":false,"errors":[{"code":10000,"message":"Authentication error"}],"messages":[]}
- no salió · @cf/black-forest-labs/flux-2-klein-9b: HTTP 401 · {"result":null,"success":false,"errors":[{"code":10000,"message":"Authentication error"}],"messages":[]}

### Qué dice Cloudflare del token

- longitud del token: **53** caracteres (lo normal son unos 40; mucho menos = se copió a medias)
- Account ID configurado: `8f4a2c…073e` (32 caracteres)
- el token **es válido y está activo** (estado: active)
- cuentas a las que llega el token: 0

El token vale pero la llamada a Workers AI da 401, así que lo que falta es el **permiso**: el token tiene que llevar `Account` → `Workers AI` → `Read`. Se arregla editando el token en https://dash.cloudflare.com/profile/api-tokens o creando uno nuevo con la plantilla **Workers AI**.

---

**0 de 2 pasaron el revisor.**

Si las fotos son Allie, Cloudflare puede sustituir a Hugging Face: unas noventa fotos al día en vez de ninguna.
