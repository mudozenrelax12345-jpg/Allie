# Prueba de Cloudflare · 20261013-1520 UTC

**Faltan credenciales.** Esto es lo que se ve:

| secreto | ¿está? | de dónde | longitud |
|---|---|---|---|
| Account ID | sí | `CF_ACCOUNT_ID` | 32 |
| API token | **NO** | `—` | — |

Los nombres buenos son `CF_ACCOUNT_ID` y `CF_API_TOKEN`, pero también valen las variantes: `CLOUDFLARE_ACCOUNT_ID`, `CF_ACCOUNT`, `CF_ID`, `CF_CUENTA`, `CLOUDFLARE_API_TOKEN`, `CF_TOKEN`, `CF_API_KEY`, `CLOUDFLARE_TOKEN`, `CF_FICHA`.

Si uno pone «NO», ese secreto no existe o está escrito con otro nombre. Se arregla en Settings → Secrets and variables → Actions.

Como referencia: el Account ID son 32 caracteres; el token, unos 40.