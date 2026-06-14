import os
import sqlite3

from sqlalchemy import create_engine, text


SQLITE_PATH = os.environ.get("SQLITE_PATH", "dear_erp.db")
DATABASE_URL = os.environ["DATABASE_URL"]


TABLES = [
    "users",
    "suppliers",
    "locations",
    "colors",
    "sizes",
    "other_specs",
    "products",
    "product_variants",
    "product_other_specs",
]

SEQUENCE_TABLES = [
    "users",
    "suppliers",
    "locations",
    "colors",
    "sizes",
    "other_specs",
    "products",
    "product_variants",
]


def sqlite_columns(cursor, table):
    return [row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()]


def postgres_columns(conn, table):
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table
            """
        ),
        {"table": table},
    ).fetchall()
    return {row[0] for row in rows}


def migrate_table(sqlite_conn, pg_conn, table):
    sqlite_cursor = sqlite_conn.cursor()
    source_columns = sqlite_columns(sqlite_cursor, table)
    target_columns = postgres_columns(pg_conn, table)
    common_columns = [column for column in source_columns if column in target_columns]

    if table == "products" and "image_filename" in source_columns and "image_path" in target_columns:
        common_columns = [column for column in common_columns if column != "image_filename"]
        common_columns.append("image_path")

    if not common_columns:
        return

    rows = sqlite_cursor.execute(f"SELECT * FROM {table}").fetchall()
    source_index = {column: index for index, column in enumerate(source_columns)}

    for row in rows:
        values = {}
        for column in common_columns:
            if column == "image_path" and "image_filename" in source_index:
                filename = row[source_index["image_filename"]]
                values[column] = f"uploads/products/{filename}" if filename else None
            else:
                values[column] = row[source_index[column]]

        columns_sql = ", ".join(values.keys())
        params_sql = ", ".join(f":{column}" for column in values.keys())
        pg_conn.execute(text(f"INSERT INTO {table} ({columns_sql}) VALUES ({params_sql}) ON CONFLICT DO NOTHING"), values)


def reset_sequence(pg_conn, table):
    pg_conn.execute(
        text(
            """
            SELECT setval(
                pg_get_serial_sequence(:table_name, 'id'),
                COALESCE((SELECT MAX(id) FROM """ + table + """), 1),
                true
            )
            """
        ),
        {"table_name": table},
    )


def main():
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_engine = create_engine(DATABASE_URL)

    with pg_engine.begin() as pg_conn:
        for table in TABLES:
            migrate_table(sqlite_conn, pg_conn, table)
        for table in SEQUENCE_TABLES:
            reset_sequence(pg_conn, table)

    sqlite_conn.close()
    print("SQLite data migrated to PostgreSQL.")


if __name__ == "__main__":
    main()
