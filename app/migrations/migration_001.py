"""
Migration 001: Home Inventory Schema

Adds: locations, item_types, attribute_definitions, inventory_items,
      item_attributes, inventory_photos tables.
Alters: bins (location_id), categories (kind).
Seeds: Guitar, Amplifier, Pedal item types and all their attribute definitions.
Migrates: bins.location text → locations table rows.

Safe to run on both fresh and existing databases. Idempotent.
"""

from sqlalchemy import text


ITEM_TYPES = [
    # (name, slug, icon, sort_order)
    ("Guitar",     "guitar",     "🎸", 1),
    ("Amplifier",  "amplifier",  "🔊", 2),
    ("Pedal",      "pedal",      "🎛️", 3),
]

# (type_slug, key, label, field_type, options_json, section, sort_order)
ATTRIBUTE_DEFINITIONS = [
    # ─── GUITAR ──────────────────────────────────────────────────────────────
    # General
    ("guitar", "pickup_selector_type", "Pickup Selector",    "text",    None, "General", 1),
    ("guitar", "number_of_strings",    "Number of Strings",  "integer", None, "General", 2),
    ("guitar", "weight",               "Weight",             "text",    None, "General", 3),
    ("guitar", "relic",                "Relic",              "select",  '["None","Light","Medium","Heavy","Natural"]', "General", 4),
    ("guitar", "case_cover",           "Case / Cover",       "text",    None, "General", 5),
    # Body
    ("guitar", "body_style",    "Body Style",     "text",   None, "Body", 10),
    ("guitar", "top_wood",      "Top Wood",       "text",   None, "Body", 11),
    ("guitar", "body_wood",     "Body Wood",      "text",   None, "Body", 12),
    ("guitar", "body_finish",   "Body Finish",    "select", '["Nitrocellulose Lacquer","Polyurethane","Polyester","Oil","Satin","Other"]', "Body", 13),
    ("guitar", "pick_guard",    "Pick Guard",     "text",   None, "Body", 14),
    ("guitar", "hardware_finish","Hardware Finish","select", '["Chrome","Nickel","Gold","Black","Relic Nickel","Other"]', "Body", 15),
    # Neck
    ("guitar", "neck_wood",       "Neck Wood",       "text",   None, "Neck", 20),
    ("guitar", "neck_finish",     "Neck Finish",     "text",   None, "Neck", 21),
    ("guitar", "neck_attachment", "Neck Attachment", "select", '["4 Bolt","3 Bolt","Set Neck","Neck Through Body","Other"]', "Neck", 22),
    ("guitar", "neck_shape",      "Neck Shape",      "text",   None, "Neck", 23),
    ("guitar", "has_skunk_stripe","Has Skunk Stripe","boolean",None, "Neck", 24),
    # Fingerboard
    ("guitar", "fingerboard_wood",    "Fingerboard Wood",     "text", None, "Fingerboard", 30),
    ("guitar", "scale_length",        "Scale Length",         "text", None, "Fingerboard", 31),
    ("guitar", "fingerboard_radius",  "Fingerboard Radius",   "text", None, "Fingerboard", 32),
    ("guitar", "fret_size",           "Fret Size",            "text", None, "Fingerboard", 33),
    ("guitar", "nut_material",        "Nut Material",         "text", None, "Fingerboard", 34),
    ("guitar", "nut_width",           "Nut Width",            "text", None, "Fingerboard", 35),
    ("guitar", "fingerboard_details", "Fingerboard Details",  "text", None, "Fingerboard", 36),
    ("guitar", "last_recondition",    "Last Recondition",     "date", None, "Fingerboard", 37),
    # Sides & Back
    ("guitar", "side_wood", "Side Wood", "text", None, "Sides & Back", 40),
    ("guitar", "back_wood", "Back Wood", "text", None, "Sides & Back", 41),
    # Bracing
    ("guitar", "bracing_pattern", "Bracing Pattern", "text", None, "Bracing", 50),
    ("guitar", "bracing_wood",    "Bracing Wood",    "text", None, "Bracing", 51),
    # Bridge
    ("guitar", "bridge_style",    "Bridge Style",    "text",   None, "Bridge", 60),
    ("guitar", "bridge_brand",    "Bridge Brand",    "text",   None, "Bridge", 61),
    ("guitar", "bridge_model",    "Bridge Model",    "text",   None, "Bridge", 62),
    ("guitar", "bridge_material", "Bridge Material", "text",   None, "Bridge", 63),
    ("guitar", "bridge_wood",     "Bridge Wood",     "text",   None, "Bridge", 64),
    ("guitar", "saddle_material", "Saddle Material", "text",   None, "Bridge", 65),
    ("guitar", "tuner_type",      "Tuner Type",      "select", '["Non-locking","Locking","Vintage","Other"]', "Bridge", 66),
    # Pickups
    ("guitar", "neck_pickup_type",  "Neck Pickup Type",  "text",     None, "Pickups — Neck", 70),
    ("guitar", "neck_pickup_brand", "Neck Pickup Brand", "text",     None, "Pickups — Neck", 71),
    ("guitar", "neck_pickup_model", "Neck Pickup Model", "text",     None, "Pickups — Neck", 72),
    ("guitar", "neck_pickup_notes", "Neck Pickup Notes", "textarea", None, "Pickups — Neck", 73),
    ("guitar", "mid_pickup_type",   "Middle Pickup Type",  "text",     None, "Pickups — Middle", 80),
    ("guitar", "mid_pickup_brand",  "Middle Pickup Brand", "text",     None, "Pickups — Middle", 81),
    ("guitar", "mid_pickup_model",  "Middle Pickup Model", "text",     None, "Pickups — Middle", 82),
    ("guitar", "mid_pickup_notes",  "Middle Pickup Notes", "textarea", None, "Pickups — Middle", 83),
    ("guitar", "bridge_pickup_type",  "Bridge Pickup Type",  "text",     None, "Pickups — Bridge", 90),
    ("guitar", "bridge_pickup_brand", "Bridge Pickup Brand", "text",     None, "Pickups — Bridge", 91),
    ("guitar", "bridge_pickup_model", "Bridge Pickup Model", "text",     None, "Pickups — Bridge", 92),
    ("guitar", "bridge_pickup_notes", "Bridge Pickup Notes", "textarea", None, "Pickups — Bridge", 93),
    ("guitar", "soundhole_pickup_type",  "Sound Hole Pickup Type",  "text",     None, "Pickups — Sound Hole", 100),
    ("guitar", "soundhole_pickup_brand", "Sound Hole Pickup Brand", "text",     None, "Pickups — Sound Hole", 101),
    ("guitar", "soundhole_pickup_model", "Sound Hole Pickup Model", "text",     None, "Pickups — Sound Hole", 102),
    ("guitar", "soundhole_pickup_notes", "Sound Hole Pickup Notes", "textarea", None, "Pickups — Sound Hole", 103),
    ("guitar", "transducer_pickup_type",  "Transducer Pickup Type",  "text",     None, "Pickups — Transducer", 110),
    ("guitar", "transducer_pickup_brand", "Transducer Pickup Brand", "text",     None, "Pickups — Transducer", 111),
    ("guitar", "transducer_pickup_model", "Transducer Pickup Model", "text",     None, "Pickups — Transducer", 112),
    ("guitar", "transducer_pickup_notes", "Transducer Pickup Notes", "textarea", None, "Pickups — Transducer", 113),
    # Electronics
    ("guitar", "wiring_notes", "Wiring Notes", "textarea", None, "Electronics", 120),
    # Strings
    ("guitar", "string_gauge_min", "Min Gauge",    "text", None, "Strings", 130),
    ("guitar", "string_gauge_max", "Max Gauge",    "text", None, "Strings", 131),
    ("guitar", "string_tuning",    "Tuning",       "text", None, "Strings", 132),
    ("guitar", "string_brand",     "String Brand", "text", None, "Strings", 133),
    ("guitar", "string_model",     "String Model", "text", None, "Strings", 134),
    ("guitar", "last_restring",    "Last Restring","date", None, "Strings", 135),
    # Maintenance
    ("guitar", "maintenance_notes", "Maintenance Notes", "textarea", None, "Maintenance", 140),

    # ─── AMPLIFIER ───────────────────────────────────────────────────────────
    # General
    ("amplifier", "kind",             "Kind",               "select",  '["Combo","Head","Cabinet"]', "General", 1),
    ("amplifier", "output_watts",     "Output Power (W)",   "integer", None, "General", 2),
    ("amplifier", "circuit_type",     "Circuit Type",       "text",    None, "General", 3),
    ("amplifier", "circuit_id",       "Circuit ID",         "text",    None, "General", 4),
    ("amplifier", "num_channels",     "Number of Channels", "integer", None, "General", 5),
    ("amplifier", "channel_switching","Channel Switching",  "boolean", None, "General", 6),
    ("amplifier", "reverb",           "Reverb",             "boolean", None, "General", 7),
    ("amplifier", "effects_loop",     "Effects Loop",       "boolean", None, "General", 8),
    ("amplifier", "master_volume",    "Master Volume",      "boolean", None, "General", 9),
    ("amplifier", "attenuator",       "Attenuator",         "boolean", None, "General", 10),
    ("amplifier", "modeling",         "Modeling",           "boolean", None, "General", 11),
    ("amplifier", "clone_of",         "Clone Of / Based On","text",    None, "General", 12),
    # Power & Bias
    ("amplifier", "tube_bias_type",   "Tube Bias Type",   "select", '["Fixed","Cathode","N/A"]', "Power & Bias", 20),
    ("amplifier", "bias_target_ma",   "Bias Target (mA)", "text",   None, "Power & Bias", 21),
    ("amplifier", "output_impedance", "Output Impedance", "text",   None, "Power & Bias", 22),
    ("amplifier", "voltage",          "Voltage",          "text",   None, "Power & Bias", 23),
    # Tubes
    ("amplifier", "power_tube_1",  "Power Tube 1",  "text", None, "Tubes", 30),
    ("amplifier", "power_tube_2",  "Power Tube 2",  "text", None, "Tubes", 31),
    ("amplifier", "preamp_tube_1", "Preamp Tube 1", "text", None, "Tubes", 32),
    ("amplifier", "preamp_tube_2", "Preamp Tube 2", "text", None, "Tubes", 33),
    ("amplifier", "preamp_tube_3", "Preamp Tube 3", "text", None, "Tubes", 34),
    ("amplifier", "preamp_tube_4", "Preamp Tube 4", "text", None, "Tubes", 35),
    ("amplifier", "preamp_tube_5", "Preamp Tube 5", "text", None, "Tubes", 36),
    ("amplifier", "rectifier_1",   "Rectifier 1",   "text", None, "Tubes", 37),
    ("amplifier", "rectifier_2",   "Rectifier 2",   "text", None, "Tubes", 38),
    # Speakers
    ("amplifier", "speaker_1",    "Speaker 1",    "text",   None, "Speakers", 40),
    ("amplifier", "speaker_2",    "Speaker 2",    "text",   None, "Speakers", 41),
    ("amplifier", "speaker_3",    "Speaker 3",    "text",   None, "Speakers", 42),
    ("amplifier", "speaker_4",    "Speaker 4",    "text",   None, "Speakers", 43),
    ("amplifier", "cabinet_back", "Cabinet Back", "select", '["Open","Closed","Semi-Open"]', "Speakers", 44),
    # Cosmetics
    ("amplifier", "covering",           "Covering",           "text",    None, "Cosmetics", 50),
    ("amplifier", "covering_color",     "Covering Color",     "text",    None, "Cosmetics", 51),
    ("amplifier", "grill_cloth_color",  "Grill Cloth Color",  "text",    None, "Cosmetics", 52),
    ("amplifier", "has_cover",          "Has Cover",          "boolean", None, "Cosmetics", 53),
    # Dimensions
    ("amplifier", "dimensions", "Dimensions (LxWxH)", "text", None, "Dimensions", 60),
    ("amplifier", "weight",     "Weight",             "text", None, "Dimensions", 61),
    # Notes
    ("amplifier", "wiring_component_notes", "Wiring / Component Notes",  "textarea", None, "Notes", 70),
    ("amplifier", "maintenance_mod_notes",  "Maintenance & Modifications","textarea", None, "Notes", 71),

    # ─── PEDAL ───────────────────────────────────────────────────────────────
    # Power
    ("pedal", "voltage",       "Voltage",          "text",    None, "Power", 1),
    ("pedal", "supply",        "Supply",           "text",    None, "Power", 2),
    ("pedal", "tip_polarity",  "Tip Polarity",     "select",  '["Center Negative","Center Positive"]', "Power", 3),
    ("pedal", "power_draw_ma", "Power Draw (mA)",  "integer", None, "Power", 4),
    # Features
    ("pedal", "true_bypass",        "True Bypass",             "boolean", None, "Features", 10),
    ("pedal", "loop",               "Loop",                    "boolean", None, "Features", 11),
    ("pedal", "expression_control", "Expression Pedal Control","boolean", None, "Features", 12),
    ("pedal", "midi_control",       "MIDI Control",            "boolean", None, "Features", 13),
    # I/O
    ("pedal", "input",  "Input",  "text", None, "I/O", 20),
    ("pedal", "output", "Output", "text", None, "I/O", 21),
    # Dimensions
    ("pedal", "dimensions", "Dimensions (LxWxH)", "text", None, "Dimensions", 30),
    ("pedal", "weight",     "Weight",             "text", None, "Dimensions", 31),
]


def _column_exists(conn, table, column):
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def run():
    from app.database import engine

    with engine.connect() as conn:
        # ── Add columns to existing tables (idempotent) ───────────────────────
        if not _column_exists(conn, "bins", "location_id"):
            conn.execute(text("ALTER TABLE bins ADD COLUMN location_id INTEGER"))

        if not _column_exists(conn, "categories", "kind"):
            conn.execute(text("ALTER TABLE categories ADD COLUMN kind TEXT NOT NULL DEFAULT 'bin'"))

        # ── Seed item_types (INSERT OR IGNORE = idempotent) ───────────────────
        for name, slug, icon, sort_order in ITEM_TYPES:
            conn.execute(text("""
                INSERT OR IGNORE INTO item_types (name, slug, icon, sort_order)
                VALUES (:name, :slug, :icon, :sort)
            """), {"name": name, "slug": slug, "icon": icon, "sort": sort_order})

        # ── Seed attribute_definitions ────────────────────────────────────────
        for type_slug, key, label, field_type, options, section, sort_order in ATTRIBUTE_DEFINITIONS:
            row = conn.execute(
                text("SELECT id FROM item_types WHERE slug = :slug"),
                {"slug": type_slug}
            ).fetchone()
            if row is None:
                continue
            conn.execute(text("""
                INSERT OR IGNORE INTO attribute_definitions
                    (item_type_id, key, label, field_type, options, section, sort_order)
                VALUES (:tid, :key, :label, :ftype, :opts, :section, :sort)
            """), {
                "tid": row[0], "key": key, "label": label, "ftype": field_type,
                "opts": options, "section": section, "sort": sort_order,
            })

        # ── Migrate bin location strings → locations table ────────────────────
        bins = conn.execute(text(
            "SELECT id, location FROM bins WHERE location IS NOT NULL AND location != '' AND location_id IS NULL"
        )).fetchall()
        location_map = {}
        for bin_id, loc_text in bins:
            loc_text = loc_text.strip()
            if not loc_text:
                continue
            if loc_text not in location_map:
                conn.execute(
                    text("INSERT INTO locations (name, kind) VALUES (:name, 'other')"),
                    {"name": loc_text}
                )
                result = conn.execute(text("SELECT last_insert_rowid()")).fetchone()
                location_map[loc_text] = result[0]
            conn.execute(
                text("UPDATE bins SET location_id = :lid WHERE id = :bid"),
                {"lid": location_map[loc_text], "bid": bin_id}
            )

        conn.commit()
        print("Migration 001 applied.")
