-- P3 — Búsqueda KNN en PostgreSQL con cube y GiST.
--
-- Ejecución recomendada (el script Python genera dry_beans_cube.csv):
--   # Primero genere dry_beans_cube.csv con p3_experimento.py.
--   psql "$DATABASE_URL" -f P3_postgresql_gist.sql
--
-- No replica datos: eso lo controla p3_experimento.py para poder medir
-- cada tamaño de colección de forma independiente.

\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS cube;

DROP TABLE IF EXISTS dry_beans;

CREATE TABLE dry_beans (
    id           SERIAL PRIMARY KEY,
    category     TEXT NOT NULL,
    features_seq CUBE NOT NULL, -- búsqueda secuencial
    features_idx CUBE NOT NULL  -- búsqueda indexada
);

CREATE TEMP TABLE dry_beans_stage (
    category TEXT NOT NULL,
    features CUBE NOT NULL
);

\copy dry_beans_stage (category, features) FROM 'dry_beans_cube.csv' WITH (FORMAT csv, HEADER true)

INSERT INTO dry_beans (category, features_seq, features_idx)
SELECT category, features, features
FROM dry_beans_stage;

CREATE INDEX dry_beans_features_idx_gist
    ON dry_beans USING GIST (features_idx);

ANALYZE dry_beans;

-- Verificaciones solicitadas por el enunciado.
SELECT COUNT(*) AS filas, cube_dim(features_seq) AS dimensiones
FROM dry_beans
GROUP BY cube_dim(features_seq);

-- Ejemplos. Reemplace <vector_consulta> por el vector del objeto Q15,
-- Q2166 o Q4768. Para que el plan pueda usar KNN-GiST, el vector debe ser
-- una constante (o un parámetro), no una subconsulta.
--
-- EXPLAIN (ANALYZE, BUFFERS)
-- SELECT id, category, features_seq <-> cube(<vector_consulta>) AS distancia
-- FROM dry_beans ORDER BY distancia LIMIT 16;
--
-- EXPLAIN (ANALYZE, BUFFERS)
-- SELECT id, category, features_idx <-> cube(<vector_consulta>) AS distancia
-- FROM dry_beans ORDER BY distancia LIMIT 16;
