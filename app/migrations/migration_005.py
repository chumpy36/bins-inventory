"""Add structured setup fields to Guitar inventory records.

Safe to run multiple times (idempotent via INSERT OR IGNORE).
"""

from sqlalchemy import text


# (key, label, field_type, sort_order)
SETUP_FIELDS = [
    ("setup_neck_relief", "Neck Relief", "text", 150),
    ("setup_relief_method", "Relief Measurement", "text", 151),
    ("setup_action_fret", "Action Measurement Fret", "integer", 152),
    ("setup_action_low_e", "Low E Action", "text", 153),
    ("setup_action_high_e", "High E Action", "text", 154),
    ("setup_action_notes", "Action Notes", "textarea", 155),
    ("setup_neck_pickup_height", "Neck Pickup Height", "text", 156),
    ("setup_middle_pickup_height", "Middle Pickup Height", "text", 157),
    ("setup_bridge_pickup_height", "Bridge Pickup Height", "text", 158),
    ("setup_intonation_notes", "Intonation", "textarea", 159),
    ("setup_tremolo_notes", "Tremolo Setup", "textarea", 160),
    ("setup_neck_shim", "Neck Shim", "text", 161),
    ("setup_status", "Setup Status", "textarea", 162),
]


def run():
    from app.database import engine

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM item_types WHERE slug = 'guitar'")
        ).fetchone()
        if row is None:
            return

        for key, label, field_type, sort_order in SETUP_FIELDS:
            conn.execute(text("""
                INSERT OR IGNORE INTO attribute_definitions
                    (item_type_id, key, label, field_type, options, section, sort_order)
                VALUES (:tid, :key, :label, :field_type, NULL, 'Setup', :sort_order)
            """), {
                "tid": row[0],
                "key": key,
                "label": label,
                "field_type": field_type,
                "sort_order": sort_order,
            })

        conn.commit()
        print("Migration 005 applied.")
