# P3 — KNN con `cube` y GiST

Se cargaron 13 611 vectores del *Dry Bean Dataset*, cada uno de 16 dimensiones.
Para cada consulta (Q15, Q2166 y Q4768) y cada `k` (2, 4, 8, 16 y 32), se ejecutó
`EXPLAIN (ANALYZE, BUFFERS)` sobre `features_seq` y `features_idx`.

## Escalabilidad

Esta tabla resume la media de las 15 combinaciones consulta–`k`, medida en una instancia
local de PostgreSQL 16. Los valores pueden cambiar entre equipos, por eso los CSV generados
por el script son la evidencia reproducible.

| Filas | Secuencial (ms) | GiST (ms) |
| ---: | ---: | ---: |
| 13 611 | 3.955 | 0.617 |
| 27 222 | 6.795 | 0.856 |
| 54 444 | 12.900 | 1.173 |
| 108 888 | 14.814 | 1.525 |

El escaneo secuencial recorre todos los vectores y su costo crece con `n`. El índice GiST
mantiene tiempos mucho menores en esta colección, aunque el costo aumenta con `k` y con la
dimensión. El gráfico correspondiente se genera como `p3_escalabilidad.svg`.

## Efecto de la dimensión

Con 20 000 vectores sintéticos y `k=16`, GiST fue claramente favorable para D=2, 4 y 8.
En esta ejecución, desde D=16 el beneficio dejó de ser consistente (D=16: 6.160 ms GiST
frente a 5.021 ms secuencial; D=32 y D=64 fueron prácticamente iguales o peores con GiST).
Por tanto, para estos datos conviene GiST hasta aproximadamente D=8; D=16 es un punto de
transición que debe validarse con el tamaño y la distribución reales.

La extensión `cube` admite como máximo 100 dimensiones. En consecuencia, D=128 no puede
ejecutarse con este tipo y se registra como no soportado en `p3_dimensiones.csv`; para un
experimento que alcance 128 se necesitaría otro tipo/extensión de vectores.
