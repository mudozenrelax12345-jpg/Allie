# ✦ Allie · piloto automático

Este repositorio hace dos cosas solo, sin que tengas que tocar nada:

1. **Responde** cada hora a los comentarios y mensajes directos de Instagram, en el idioma de cada persona y con la voz de Allie. Lo que es delicado no lo contesta: te abre un aviso en **Issues**.
2. **Monta un reel** cada domingo: inventa la idea, crea las fotos de Allie con Pollinations, las convierte en vídeo vertical y deja el enlace preparado para que Claude lo programe en Metricool como *Trial Reel* (Instagram los enseña solo a quien todavía no te sigue).

Las publicaciones normales se programan aparte, desde Metricool.

**Coste: 0 €.** GitHub, Pollinations y los textos de Gemini están en sus planes gratuitos.

---

## Lo que falta para que arranque

### 1. Las claves (Settings → Secrets and variables → Actions → New repository secret)

| Nombre | De dónde sale |
|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey). No hace falta activar la facturación: aquí solo se usa para escribir texto. |
| `POLLINATIONS_KEY` | La clave de [enter.pollinations.ai](https://enter.pollinations.ai) (la que empieza por `sk_`). |
| `META_APP_SECRET` | La clave secreta de la app de Meta (Configuración → Básica → *Mostrar*). |
| `FB_TOKEN` | Mira el apartado de abajo. |

### 2. El token de Meta

Hacen falta tres cosas: la cuenta de Instagram **profesional**, una **página de
Facebook** vinculada a ella, y una app en Meta for Developers. Esta vía —la API
Graph de Facebook— es la que deja leer los comentarios de otras personas **sin
pasar por la revisión de la app**.

1. En la app de Meta: **Instagram → Configuración de la API con inicio de sesión de Facebook**, y pulsa los botones azules que añaden los permisos.
2. Abre el [Explorador de la API Graph](https://developers.facebook.com/tools/explorer/).
3. En **App de Meta** elige tu app, y en **Usuario o página** elige *Token de acceso de usuario*.
4. En **Agregar un permiso** marca estos seis:
   - `instagram_basic`
   - `instagram_manage_comments` ← los comentarios
   - `instagram_manage_messages` ← los mensajes
   - `pages_show_list`
   - `pages_read_engagement`
   - `business_management`
5. Pulsa **Generate Access Token** y acepta, marcando la página y la cuenta de Instagram.
6. Copia el token y guárdalo como el secreto `FB_TOKEN`.

Ese token dura solo unas horas, pero **en la primera ejecución el programa lo
cambia por el token de la página, que no caduca**, y lo guarda cifrado en
`estado/credenciales.json`. A partir de ahí no hay que tocar nada. Si algún día
dejara de valer (por cambiar la contraseña o retirar los permisos), te avisaría
en Issues y bastaría con repetir estos pasos.

### 3. Comprobar que todo va

Pestaña **Actions** → **Respuestas de Allie** → **Run workflow** → elige `probar`. En un minuto aparece en **Issues** un informe diciendo qué funciona ✅ y qué no ❌.

### 4. Avisos en el móvil

En el repositorio, pulsa **Watch → All Activity**, e instala la app **GitHub** en el móvil.

---

## Qué contesta y qué no

| Mensaje | Qué hace |
|---|---|
| Piropos, emojis, preguntas sobre la foto, la ropa, el sitio, las mascotas | ✅ Responde |
| «¿Eres real?» | ✅ Responde con honestidad: es un personaje creado con IA |
| Marcas, colaboraciones, dinero, ventas | ⚠️ Te avisa |
| Insultos, acoso, insinuaciones subidas de tono | ⚠️ Te avisa |
| Alguien que parece menor de edad | ⚠️ Te avisa |
| Peticiones de tu teléfono, dirección o quedar | ⚠️ Te avisa |
| Política, religión, salud, dinero, o alguien que lo pasa mal | ⚠️ Te avisa |
| Spam y bots | 🚫 Los ignora |

---

## Ajustar cómo es Allie

Todo está en **`personaje.yml`**: su forma de hablar, sus datos, qué temas evita, la foto de referencia que mantiene su cara, y los temas de los que salen los reels. Edítalo con el lápiz ✏️ y se aplica en la siguiente ejecución.

---

## Bueno saber

- **Mensajes:** Instagram solo deja contestarlos durante **24 horas** desde que la persona escribe. Como esto se ejecuta cada hora, casi siempre llega.
- **Tope por ejecución:** 30 comentarios y 20 mensajes, para no saturar los límites de Instagram.
- **Reels:** si un domingo Pollinations se queda sin saldo gratuito, verás un aviso en Issues y esa semana no habrá reel.
- **Minutos de GitHub:** el plan gratuito da 2.000 al mes para repositorios privados. Esto gasta unos 750. Si te quedaras corta, cambia en `.github/workflows/respuestas.yml` el `cron: "20 * * * *"` por `cron: "20 */2 * * *"` (cada 2 horas).
- **Para parar algo:** Actions → el workflow → botón `···` → **Disable workflow**.
