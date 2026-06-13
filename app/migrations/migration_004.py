"""
Migration 004: Add new gear item types — Miscellaneous, Pro Audio,
Cables & Adapters.

Catch-all / general types for gear that doesn't fit Guitar / Amplifier / Pedal.
They carry no type-specific attribute definitions — the common fields (name,
brand, model, year, color, condition, serial, financials, rating, story, notes)
are enough.

Safe to run multiple times (idempotent via INSERT OR IGNORE on unique slug).
"""

from sqlalchemy import text

# (name, slug, icon, sort_order)
NEW_TYPES = [
    ("Miscellaneous",      "misc",            "🧰", 4),
    ("Pro Audio",          "pro-audio",       "🎚️", 5),
    ("Cables & Adapters",  "cables-adapters", "🔌", 6),
]


def run():
    from app.database import engine

    with engine.connect() as conn:
        for name, slug, icon, sort_order in NEW_TYPES:
            conn.execute(text("""
                INSERT OR IGNORE INTO item_types (name, slug, icon, sort_order)
                VALUES (:name, :slug, :icon, :sort)
            """), {"name": name, "slug": slug, "icon": icon, "sort": sort_order})
        conn.commit()
        print("Migration 004 applied.")
