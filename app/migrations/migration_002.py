"""
Migration 002: Fix duplicate attribute definitions, consolidate pickup sections,
               add datalist suggestions to text fields.

Safe to run multiple times (idempotent).
"""

import json
from sqlalchemy import text


PICKUP_TYPES = [
    "Single Coil", "Humbucker", "P-90", "Mini Humbucker", "Lipstick",
    "Soap Bar", "Gold Foil", "Filtertron", "Blade",
    "Active Humbucker", "Active Single Coil", "Piezo", "Hex Piezo",
]

WOOD_OPTIONS = [
    "Mahogany", "Alder", "Ash", "Swamp Ash", "Basswood", "Poplar",
    "Maple", "Koa", "Walnut", "Spruce", "Cedar", "Nato", "Agathis",
    "Rosewood", "Ebony", "Pau Ferro", "Wenge", "Ovangkol",
]

NECK_SHAPES = [
    "C Shape", "Modern C", "Slim C", "U Shape",
    "V Shape", "Soft V", "Hard V", "D Shape", "Asymmetric",
]

FRET_SIZES = [
    "Vintage Narrow (6230)", "Small Medium (6105)", "Medium (6150)",
    "Medium Jumbo (6130)", "Jumbo (6100)", "Super Jumbo (6000)", "Stainless Steel",
]

FINGERBOARD_RADII = [
    '7.25"', '9.5"', '10"', '12"', '14"', '15"', '16"', '20"',
    'Compound 9.5"-14"', 'Compound 10"-16"',
]

NUT_MATERIALS = [
    "Bone", "Synthetic Bone", "TUSQ", "Graph Tech Black TUSQ",
    "Corian", "Brass", "Aluminum", "Ebony", "Locking",
]

STRING_TUNINGS = [
    "Standard (EADGBE)", "Drop D (DADGBE)", "Half Step Down (Eb)",
    "Full Step Down (D)", "Drop C (CADGBE)", "Open G (DGDGBD)",
    "Open D (DADF#AD)", "Open E (EBEG#BE)", "Open A (EAEAC#E)", "DADGAD",
]

SCALE_LENGTHS = ['24.75"', '25"', '25.5"', '26.5"', '27"', '28"', '30"', '34"']

# (key, datalist_options) — only applied to 'text' typed rows
DATALIST_FIELDS = [
    ("neck_pickup_type",       PICKUP_TYPES),
    ("mid_pickup_type",        PICKUP_TYPES),
    ("bridge_pickup_type",     PICKUP_TYPES),
    ("soundhole_pickup_type",  PICKUP_TYPES),
    ("transducer_pickup_type", PICKUP_TYPES),
    ("top_wood",               WOOD_OPTIONS),
    ("body_wood",              WOOD_OPTIONS),
    ("neck_wood",              WOOD_OPTIONS),
    ("fingerboard_wood",       WOOD_OPTIONS),
    ("side_wood",              WOOD_OPTIONS),
    ("back_wood",              WOOD_OPTIONS),
    ("bracing_wood",           WOOD_OPTIONS),
    ("bridge_wood",            WOOD_OPTIONS),
    ("neck_shape",             NECK_SHAPES),
    ("fret_size",              FRET_SIZES),
    ("fingerboard_radius",     FINGERBOARD_RADII),
    ("scale_length",           SCALE_LENGTHS),
    ("nut_material",           NUT_MATERIALS),
    ("string_tuning",          STRING_TUNINGS),
]


def run():
    from app.database import engine

    with engine.connect() as conn:

        # ── Step 1: Deduplicate attribute_definitions ─────────────────────────
        # Remap any item_attributes that reference soon-to-be-deleted dup rows
        conn.execute(text("""
            UPDATE item_attributes
            SET attribute_def_id = (
                SELECT MIN(ad2.id)
                FROM attribute_definitions ad2
                WHERE ad2.item_type_id = (
                    SELECT item_type_id FROM attribute_definitions WHERE id = item_attributes.attribute_def_id
                )
                AND ad2.key = (
                    SELECT key FROM attribute_definitions WHERE id = item_attributes.attribute_def_id
                )
            )
            WHERE attribute_def_id NOT IN (
                SELECT MIN(id) FROM attribute_definitions GROUP BY item_type_id, key
            )
        """))

        # Delete all non-canonical duplicates
        conn.execute(text("""
            DELETE FROM attribute_definitions
            WHERE id NOT IN (
                SELECT MIN(id) FROM attribute_definitions GROUP BY item_type_id, key
            )
        """))

        # Add a unique index so INSERT OR IGNORE in migration_001 actually works
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_attr_def_type_key
            ON attribute_definitions(item_type_id, key)
        """))

        # ── Step 2: Consolidate pickup sections ───────────────────────────────
        conn.execute(text("""
            UPDATE attribute_definitions
            SET section = 'Pickups'
            WHERE section LIKE 'Pickups — %'
        """))

        # Move pickup_selector_type from "General" into "Pickups", ordered first
        conn.execute(text("""
            UPDATE attribute_definitions
            SET section = 'Pickups', sort_order = 69
            WHERE key = 'pickup_selector_type'
        """))

        # ── Step 3: Add datalist field_type and options ───────────────────────
        for key, options in DATALIST_FIELDS:
            conn.execute(text("""
                UPDATE attribute_definitions
                SET field_type = 'datalist', options = :opts
                WHERE key = :key AND field_type = 'text'
            """), {"key": key, "opts": json.dumps(options)})

        conn.commit()
        print("Migration 002 applied.")
