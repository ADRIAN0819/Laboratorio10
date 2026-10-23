#!/usr/bin/env python3
"""Automatiza P3 sin dependencias externas.

Convierte el XLSX de Dry Bean a CSV, crea la tabla con cube/GiST y mide KNN.
Ejemplo:
  python3 p3_experimento.py --dsn "$DATABASE_URL" --replicas 1,2,4,8
"""

import argparse
import csv
import json
import re
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
FEATURES = 16
QUERY_IDS = (16, 2167, 4769)  # Q15, Q2166 y Q4768: notebook usa índices desde 0.
KS = (2, 4, 8, 16, 32)


def shared_strings(book):
    try:
        root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(si.itertext()) for si in root.findall("x:si", NS)]


def xlsx_rows(xlsx_path):
    with zipfile.ZipFile(xlsx_path) as book:
        strings = shared_strings(book)
        root = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
    for row in root.findall(".//x:sheetData/x:row", NS):
        values = []
        for cell in row.findall("x:c", NS):
            value = cell.findtext("x:v", default="", namespaces=NS)
            if cell.get("t") == "s":
                value = strings[int(value)]
            values.append(value)
        yield values


def make_csv(xlsx_path, csv_path):
    rows = xlsx_rows(xlsx_path)
    header = next(rows)
    if len(header) != FEATURES + 1:
        raise ValueError(f"Se esperaban 16 atributos y una clase; se hallaron {len(header)} columnas")
    count = 0
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["features"])
        for row in rows:
            if len(row) != FEATURES + 1:
                raise ValueError(f"Fila inválida: {row!r}")
            # La última columna es la clase; P3 solo almacena el vector de 16 atributos.
            writer.writerow(["(" + ",".join(row[:FEATURES]) + ")"])
            count += 1
    return count


def run_psql(dsn, sql, capture=True):
    completed = subprocess.run(
        ["psql", dsn, "-X", "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
        text=True, capture_output=capture, check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def prepare_database(dsn, csv_path):
    script = Path(__file__).with_name("P3_postgresql_gist.sql")
    expected_csv = Path.cwd() / "dry_beans_cube.csv"
    if csv_path.resolve() != expected_csv.resolve():
        raise ValueError("P3_postgresql_gist.sql carga dry_beans_cube.csv; use el nombre CSV por defecto")
    completed = subprocess.run(
        ["psql", dsn, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(script)],
        text=True, capture_output=True, check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())


def cube_for_id(dsn, item_id):
    cube = run_psql(dsn, f"SELECT features_idx::text FROM dry_beans WHERE id = {item_id};")
    if not re.fullmatch(r"\([^()]+\)", cube):
        raise ValueError(f"No se encontró un vector válido para id={item_id}")
    return cube


def explain_ms(dsn, column, vector, k, table="dry_beans"):
    sql = (
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
        f"SELECT id FROM {table} ORDER BY {column} <-> cube('{vector}') LIMIT {k};"
    )
    plan = json.loads(run_psql(dsn, sql))[0]
    return plan["Execution Time"], plan["Plan"].get("Node Type", "desconocido")


def replicate_to(dsn, target_rows):
    current = int(run_psql(dsn, "SELECT count(*) FROM dry_beans;"))
    while current < target_rows:
        # Duplicar la tabla completa conserva exactamente los mismos vectores.
        run_psql(dsn, "INSERT INTO dry_beans (features_seq, features_idx) "
                      "SELECT features_seq, features_idx FROM dry_beans;")
        current = int(run_psql(dsn, "SELECT count(*) FROM dry_beans;"))
    run_psql(dsn, "ANALYZE dry_beans;")
    return current


def write_scalability_chart(records, output=Path("p3_escalabilidad.svg"),
                            title="KNN: tiempo medio de ejecución", xlabel="número de filas"):
    """Crea un gráfico SVG portátil del tiempo medio para cada tamaño."""
    grouped = {}
    for row in records:
        if row["ms"] is not None:
            grouped.setdefault((row["filas"], row["metodo"]), []).append(row["ms"])
    sizes = sorted({size for size, _ in grouped})
    methods = ("secuencial", "GiST")
    means = {(size, method): statistics.mean(grouped[size, method])
             for size in sizes for method in methods}
    maximum = max(means.values()) * 1.12
    left, top, width, height = 70, 30, 650, 310

    def point(index, value):
        x = left + width / 2 if len(sizes) == 1 else left + index * width / (len(sizes) - 1)
        y = top + height - value / maximum * height
        return x, y

    colors = {"secuencial": "#d95f02", "GiST": "#1b9e77"}
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="420" viewBox="0 0 800 420">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="400" y="20" text-anchor="middle" font-family="sans-serif" font-size="16">{title}</text>',
        f'<line x1="{left}" y1="{top + height}" x2="{left + width}" y2="{top + height}" stroke="black"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + height}" stroke="black"/>',
    ]
    for tick in range(5):
        value = maximum * tick / 4
        y = top + height - height * tick / 4
        parts += [f'<line x1="{left}" y1="{y:.1f}" x2="{left + width}" y2="{y:.1f}" stroke="#ddd"/>',
                  f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11">{value:.1f}</text>']
    for index, size in enumerate(sizes):
        x, _ = point(index, 0)
        parts.append(f'<text x="{x:.1f}" y="{top + height + 20}" text-anchor="middle" font-family="sans-serif" font-size="11">{size}</text>')
    for method in methods:
        coords = " ".join(f"{x:.1f},{y:.1f}" for index, size in enumerate(sizes)
                          for x, y in [point(index, means[size, method])])
        parts.append(f'<polyline fill="none" stroke="{colors[method]}" stroke-width="3" points="{coords}"/>')
        for index, size in enumerate(sizes):
            x, y = point(index, means[size, method])
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{colors[method]}"/>')
    parts += [
        f'<text x="400" y="408" text-anchor="middle" font-family="sans-serif" font-size="12">{xlabel}</text>',
        f'<text x="{left + width - 130}" y="48" font-family="sans-serif" font-size="12" fill="{colors["secuencial"]}">● secuencial</text>',
        f'<text x="{left + width - 130}" y="64" font-family="sans-serif" font-size="12" fill="{colors["GiST"]}">● GiST</text>',
        '</svg>',
    ]
    output.write_text("\n".join(parts), encoding="utf-8")
    return output


def dimension_experiment(dsn, rows):
    """Compara scan y GiST con datos uniformes, D=2 hasta D=128."""
    dimensions = (2, 4, 8, 16, 32, 64, 128)
    records = []
    for dimension in dimensions:
        if dimension > 100:
            # cube limita sus vectores a 100 dimensiones; se conserva el
            # resultado para documentar la limitación del experimento pedido.
            for method in ("secuencial", "GiST"):
                records.append({"filas": dimension, "dimension": dimension, "datos": rows,
                                "k": 16, "metodo": method, "ms": None,
                                "nodo_plan": "cube admite como máximo 100 dimensiones"})
            print(f"D={dimension:3d}: no soportado por la extensión cube (máximo 100)")
            continue
        run_psql(dsn, "DROP TABLE IF EXISTS synthetic_vectors;")
        run_psql(dsn, "CREATE TABLE synthetic_vectors (id serial PRIMARY KEY, "
                      "features_seq cube NOT NULL, features_idx cube NOT NULL);")
        # La referencia a row_id hace que el arreglo aleatorio se evalúe para cada fila.
        run_psql(dsn, f"INSERT INTO synthetic_vectors (features_seq, features_idx) "
                      f"SELECT cube(v), cube(v) FROM generate_series(1, {rows}) AS row_id "
                      f"CROSS JOIN LATERAL (SELECT array_agg(random()) AS v "
                      f"FROM generate_series(1, {dimension}) AS dim_id WHERE row_id IS NOT NULL) AS values;")
        run_psql(dsn, "CREATE INDEX synthetic_vectors_gist ON synthetic_vectors USING GIST (features_idx);")
        run_psql(dsn, "ANALYZE synthetic_vectors;")
        vector = run_psql(dsn, "SELECT features_idx::text FROM synthetic_vectors WHERE id = 1;")
        for method, column in (("secuencial", "features_seq"), ("GiST", "features_idx")):
            milliseconds, node = explain_ms(dsn, column, vector, 16, "synthetic_vectors")
            records.append({"filas": dimension, "dimension": dimension, "datos": rows,
                            "k": 16, "metodo": method, "ms": milliseconds, "nodo_plan": node})
            print(f"D={dimension:3d} n={rows:6d} {method:10s} {milliseconds:9.3f} ms [{node}]")
    output = Path("p3_dimensiones.csv")
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    chart = write_scalability_chart(records, Path("p3_dimensiones.svg"),
                                    "KNN: efecto de la dimensión (k=16)", "dimensión D")
    print(f"Experimento por dimensión: {output}, {chart}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True, help="DSN o URL de PostgreSQL")
    parser.add_argument("--xlsx", type=Path, default=Path("Dry_Bean_Dataset.xlsx"))
    parser.add_argument("--csv", type=Path, default=Path("dry_beans_cube.csv"))
    parser.add_argument("--replicas", default="1,2,4,8", help="factores de tamaño separados por coma")
    parser.add_argument("--synthetic-rows", type=int, default=20000,
                        help="filas aleatorias para cada dimensión (por defecto: 20000)")
    parser.add_argument("--skip-dimensions", action="store_true",
                        help="omite el experimento sintético D=2..128")
    args = parser.parse_args()

    base_rows = make_csv(args.xlsx, args.csv)
    print(f"CSV creado: {args.csv} ({base_rows} vectores de {FEATURES} dimensiones)")
    prepare_database(args.dsn, args.csv.resolve())

    factors = [int(value) for value in args.replicas.split(",")]
    if factors != sorted(set(factors)) or factors[0] != 1:
        raise ValueError("--replicas debe ser una lista ascendente que empiece en 1")

    records = []
    for factor in factors:
        total = replicate_to(args.dsn, base_rows * factor)
        for query_id in QUERY_IDS:
            vector = cube_for_id(args.dsn, query_id)
            for k in KS:
                for method, column in (("secuencial", "features_seq"), ("GiST", "features_idx")):
                    milliseconds, node = explain_ms(args.dsn, column, vector, k)
                    records.append({"filas": total, "factor": factor, "consulta": f"Q{query_id - 1}",
                                    "k": k, "metodo": method, "ms": milliseconds, "nodo_plan": node})
                    print(f"n={total:6d} Q{query_id - 1} k={k:2d} {method:10s} {milliseconds:9.3f} ms [{node}]")

    output = Path("p3_resultados.csv")
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    print(f"Resultados guardados en {output}")
    print(f"Gráfico guardado en {write_scalability_chart(records)}")
    if not args.skip_dimensions:
        dimension_experiment(args.dsn, args.synthetic_rows)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
