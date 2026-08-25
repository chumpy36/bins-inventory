"""Add creator attribution to API-managed records."""

from sqlalchemy import text


TABLES = ("bins", "items", "inventory_items", "locations")


def run():
    from app.database import engine

    with engine.begin() as conn:
        for table in TABLES:
            columns = {
                row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))
            }
            if "created_by" not in columns:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN created_by VARCHAR"))

    print("Migration 006 applied.")
