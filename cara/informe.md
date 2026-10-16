# Comprobación de cara (OpenCV, sin API)

Umbral: **0.5**

## Fotos de Allie (deben pasar)

- ✅ 20261016-114001-3.jpg · parecido 0.799
- ✅ 20261016-113630-3.jpg · parecido 0.562
- ✅ 20261016-113523-3.jpg · parecido 0.649
- ✅ 20261016-060842-3.jpg · parecido 0.823
- ✅ 20261016-043429-3.jpg · parecido 0.737
- ✅ 20261016-043314-3.jpg · parecido 0.657
- ✅ 20261016-043202-3.jpg · parecido 0.661
- ✅ 20261015-171718-3.jpg · parecido 0.683
- ✅ 20261015-171529-3.jpg · parecido 0.570
- ✅ 20261015-171234-3.jpg · parecido 0.662
- ✅ 20261015-061234-3.jpg · parecido 0.531
- ✅ 20261015-061006-3.jpg · parecido 0.565
- ✅ foto-20261008-1408-1.jpg · parecido 0.889
- ✅ foto-20261008-1408-2.jpg · parecido 0.798
- ✅ foto-20261007-2155.jpg · parecido 0.889

## La desconocida (debe fallar)

- ✅ sana-sin-referencia.jpg NO pasa · parecido 0.411
- ✅ sana-con-foto-de-referencia.jpg NO pasa · parecido 0.411

**Reparto**: la peor foto de Allie saca 0.531, la mejor desconocida 0.411, y el umbral está en 0.5

- ✅ el umbral deja fuera a todas las desconocidas · 0.411 vs 0.5
- ✅ y deja dentro a todas las de Allie · 0.531 vs 0.5

**0 fallos.**

