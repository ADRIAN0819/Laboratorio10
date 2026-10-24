# Laboratorio 10 - Búsqueda por Similitud

La entrega integrada está en `Laboratorio10_completo.ipynb`; contiene P1, P2 y las
instrucciones reproducibles de P3.

## P1. Búsqueda por Rango

- `P1_busqueda_rango.ipynb`: búsqueda lineal por rango con distancia euclidiana sobre el Dry Bean Dataset (consultas Q15, Q2166, Q4768 y 5 radios).
- `Dry_Bean_Dataset.xlsx`: dataset usado por el notebook.

Requisitos: `numpy`, `pandas`, `matplotlib`, `openpyxl`.

## P3. KNN en PostgreSQL con `cube` y GiST

Los archivos `P3_postgresql_gist.sql` y `p3_experimento.py` implementan la parte
de PostgreSQL del enunciado. El script no necesita paquetes de Python: convierte el
XLSX a vectores `cube` de 16 dimensiones, crea el índice GiST, ejecuta `EXPLAIN
ANALYZE` para `k = 2, 4, 8, 16, 32`, guarda las mediciones en
`p3_resultados.csv` y genera el gráfico de escalabilidad `p3_escalabilidad.svg`.
También ejecuta el experimento sintético D=2, 4, …, 128 (k=16) y produce
`p3_dimensiones.csv` y `p3_dimensiones.svg`. La extensión `cube` de PostgreSQL
admite hasta 100 dimensiones, por lo que D=128 queda registrado como no soportado;
es un hallazgo que debe indicarse en el análisis. Use `--skip-dimensions` para omitirlo.

Con PostgreSQL en ejecución y una base de datos vacía:

```bash
python3 p3_experimento.py --dsn 'postgresql://usuario:clave@localhost:5432/bd2'
```

Las consultas Q15, Q2166 y Q4768 se convierten a los ids 16, 2167 y 4769 porque
el notebook usa índices basados en cero, mientras que PostgreSQL usa `SERIAL` desde 1.
