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
| `INSTAGRAM_TOKEN` | Mira el apartado de abajo. |

### 2. El token de Instagram

Tu cuenta tiene que ser **profesional** (Empresa o Creador).

1. Entra en [developers.facebook.com](https://developers.facebook.com) con tu Facebook y regístrate como desarrolladora (gratis).
2. **Mis apps → Crear app**. Cuando pregunte el caso de uso, elige el de **Instagram**.
3. Dentro de la app: **Instagram → Configuración de la API con inicio de sesión de Instagram**.
4. En **Generar tokens de acceso**, pulsa **Añadir cuenta** y entra con la cuenta de Allie.
5. **Acepta los tres permisos**:
   - `instagram_business_basic`
   - `instagram_business_manage_comments` ← los comentarios
   - `instagram_business_manage_messages` ← los mensajes
   - Si te pide aceptar una invitación de *tester*: en Instagram, Configuración → Apps y sitios web → Invitaciones de tester → acéptala.
6. Pulsa **Generar token**, cópialo y guárdalo como el secreto `INSTAGRAM_TOKEN`.

El token dura 60 días, pero **se renueva solo cada semana**. Si dejara de valer, te avisaría en Issues.

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
