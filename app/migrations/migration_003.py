"""
Migration 003: Add Todo textarea to Guitar and Amplifier item types.

Safe to run multiple times (idempotent via INSERT OR IGNORE).
"""

from sqlalchemy import text


def run():
    from app.database import engine

    with engine.connect() as conn:
        for type_slug, section, sort_order in [
            ("guitar",    "Maintenance", 141),
            ("amplifier", "Notes",        72),
        ]:
            row = conn.execute(
                text("SELECT id FROM item_types WHERE slug = :slug"),
                {"slug": type_slug}
            ).fetchone()
            if row is None:
                continue
            conn.execute(text("""
                INSERT OR IGNORE INTO attribute_definitions
                    (item_type_id, key, label, field_type, options, section, sort_order)
                VALUES (:tid, 'todo', 'Todo', 'textarea', NULL, :section, :sort)
            """), {"tid": row[0], "section": section, "sort": sort_order})

        conn.commit()
        print("Migration 003 applied.")
