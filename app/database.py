import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/bins.db")

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
