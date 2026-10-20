# 🎬 Canal · fábrica de narración

Convierte un guion en pistas de audio listas para montar. **Coste: 0 €.**

No tienes que instalar nada en tu ordenador: todo se ejecuta en GitHub.

---

## Cómo se usa

1. Pestaña **Actions** → **Generar narración** → **Run workflow**.
2. Elige la voz y pulsa el botón verde.
3. En unos minutos, al final de la página, aparece **narracion-…** para descargar.

Dentro del zip:

| Archivo | Para qué |
|---|---|
| `01-acto-1-el-gancho.wav` … | Un archivo por acto. Los arrastras al montaje por separado |
| `completo.wav` | Todo seguido, por si prefieres montar sobre una sola pista |
| `marcas.txt` | **Lo que de verdad ahorra tiempo:** en qué minuto y segundo empieza cada frase |

`marcas.txt` tiene este aspecto:

```
00:00.00  ═══ Acto 1 · El gancho
00:00.00      Adam Foley returned a rental car in Atlanta last summer…
00:07.41      He got an automated message. Three hundred and fifty…
```

Así, cuando toque poner la carta del Congreso en pantalla, sabes el segundo exacto
sin tener que buscarlo a oído.

---

## Las voces

| Voz | Cómo suena |
|---|---|
| `af_heart` | Mujer, cálida. **La mejor para documental** |
| `af_bella` | Mujer, más grave |
| `am_michael` | Hombre, neutro |
| `am_fenrir` | Hombre, más grave |
| `bf_emma` · `bm_george` | Acento británico |

Prueba dos o tres con el primer acto antes de decidir. Cada ejecución cuesta
unos minutos de GitHub y los tienes de sobra.

La velocidad por defecto es **0,95** — un pelín más lento de lo normal, que es
como suenan los documentales. Si te parece soporífero, súbela a 1,0.

---

## Escribir un guion nuevo

Guárdalo en `guiones/` con extensión `.md`. Solo dos reglas:

- Cada bloque hablado va bajo un título que empiece por **`### Acto`**
- Cada línea que se lee en alto empieza por **`> `**

Todo lo demás —acotaciones de imagen, notas, enlaces— se ignora. Puedes escribir
lo que quieras alrededor sin miedo a que acabe en el audio.

**Para que la voz suene bien:** cifras en letra (*twenty-seven billion*, no *27bn*),
frases cortas, y pausas con punto y aparte en vez de comas.

---

## Subir a YouTube

**Esto sí lo hace, desde el 20 de octubre de 2026.** Antes no, y el motivo
está escrito aquí porque conviene no olvidarlo: desde julio de 2020 los
vídeos subidos por una API sin auditar quedaban bloqueados como privados y
no había apelación. Era el único paso de toda la fábrica que necesitaba a
una persona delante, y por eso el canal se paró a los tres vídeos.

Esa regla ya no está. La documentación oficial de `videos.insert` dice ahora:

> Videos uploaded from unverified API projects are not restricted to private
> viewing mode.

Y las subidas tienen su propio cubo de cuota: **100 vídeos al día**, que no
gastan nada de las 10.000 unidades diarias del resto de la API.

Se sube con **Subir a YouTube** en Actions, o marcando `subir` al montar.
Cada vídeo lleva su ficha en `videos/<id>/youtube.yml`: título, descripción,
etiquetas, miniatura.

### El paso que mata el canal si se salta

La aplicación de Google tiene que estar en **«In production»**, no en
«Testing». Palabras de Google:

> A Google Cloud Platform project with an OAuth consent screen configured for
> an external user type and a publishing status of "Testing" is issued a
> refresh token expiring in 7 days.

En «Testing», la llave se muere sola a los siete días y el canal deja de
publicar en silencio. Hay un workflow, **¿Sigue viva la llave de YouTube?**,
que la comprueba todos los lunes y abre un aviso si se ha muerto.

## Lo que NO hace esto

- **No monta el vídeo en Kdenlive.** El montaje automático da un primer corte
  decente; retocarlo a mano sigue siendo cosa tuya si quieres afinar.

---

## Claves

Ninguna. Kokoro se descarga solo y es de licencia Apache, que permite uso comercial.
