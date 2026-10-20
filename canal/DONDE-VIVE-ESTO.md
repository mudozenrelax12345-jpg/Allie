# Por qué el canal vive dentro del repositorio de Allie

**20 de octubre de 2026.**

El canal **Rounding Error** tiene su propio repositorio,
`mudozenrelax12345-jpg/canal`. Esta carpeta es una copia de aquello, y a
partir de hoy es **la copia viva**: lo que se toque, se toca aquí.

## El motivo, que es puramente de dinero

Aquel repositorio es **privado**. Los repositorios privados traen 2.000
minutos de GitHub Actions al mes. Los montajes de vídeo son largos —el
flujo tiene un tope de 150 minutos— y entre los tres primeros vídeos se
agotaron. Desde entonces cualquier ejecución allí muere en cinco segundos:

> The job was not started because recent account payments have failed or
> your spending limit needs to be increased.

En un repositorio **público**, Actions es gratis y sin tope de minutos.
Este lo es. Así que en vez de pagar, o de esperar al 1 de noviembre, la
maquinaria se trae aquí.

Se valoró cambiar el otro repositorio a público, que era lo más limpio.
Antes de hacerlo se reescribieron sus 33 commits para quitar el correo
personal de Teresa del historial, que iba a quedar a la vista. Pero el
cambio de visibilidad no llegó a completarse —GitHub pide pasar por dos
ventanas de confirmación— y a esas horas era más fácil mover la carpeta
que pelearse con la Danger Zone desde el móvil.

## Qué NO se ha mezclado

Nada. El canal vive entero en `canal/`, con su `app/`, sus `guiones/`, sus
`videos/` y su `requirements.txt`. Los flujos del canal se llaman
`canal-*.yml` y tienen su propio grupo de concurrencia, así que un montaje
del canal no bloquea una publicación de Allie ni al revés.

## Qué pasa con el repositorio viejo

Queda congelado. No se borra —es el historial de cómo se hizo— pero no se
toca más. Si algún día se hace público y se quieren recuperar allí los
Actions, lo que hay aquí se puede devolver tal cual.

## Lo que falta para que el canal publique solo

Las tres claves de YouTube en los secretos de **este** repositorio:
`YT_CLIENT_ID`, `YT_CLIENT_SECRET` y `YT_REFRESH_TOKEN`. Sin ellas se
montan los Shorts pero no se suben. El procedimiento está en
`canal/README.md`, y el paso que no se puede saltar es dejar la aplicación
de Google en «In production»: en «Testing», Google caduca la llave a los
siete días y el canal se muere solo y en silencio.
