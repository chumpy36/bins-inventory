import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(os.getenv('DATA_DIR', DEFAULT_DATA_DIR), 'bins.db')}",
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models import (  # noqa: F401
        Category, Bin, Item, Photo,
        Location, ItemType, AttributeDefinition,
        InventoryItem, ItemAttribute, InventoryPhoto,
        AISuggestion,
    )
    # Create all tables that don't exist yet (safe for both fresh and existing DBs)
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
                bin_token,
                bin_name,
                item_names,
                content=''
            )
        """))
        conn.commit()

    # Add new columns and seed data (idempotent)
    from app.migrations.migration_001 import run as run_001
    run_001()

    from app.migrations.migration_002 import run as run_002
    run_002()

    from app.migrations.migration_003 import run as run_003
    run_003()

    from app.migrations.migration_004 import run as run_004
    run_004()

    from app.migrations.migration_005 import run as run_005
    run_005()

    from app.migrations.migration_006 import run as run_006
    run_006()
