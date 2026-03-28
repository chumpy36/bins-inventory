import secrets
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def generate_token():
    return secrets.token_urlsafe(6)  # ~8 chars, URL-safe


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    color = Column(String, default="#6366f1")  # indigo default
    created_at = Column(DateTime, default=utcnow)

    bins = relationship("Bin", back_populates="category", order_by="Bin.name")


class Bin(Base):
    __tablename__ = "bins"

    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, nullable=False, default=generate_token)
    name = Column(String, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    location = Column(String, nullable=True)  # e.g. "Shed shelf 2"
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    category = relationship("Category", back_populates="bins")
    items = relationship("Item", back_populates="bin", order_by="Item.name", cascade="all, delete-orphan")
    photos = relationship("Photo", back_populates="bin", order_by="Photo.sort_order", cascade="all, delete-orphan")


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    bin_id = Column(Integer, ForeignKey("bins.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    quantity = Column(Integer, default=1)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    bin = relationship("Bin", back_populates="items")


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True)
    bin_id = Column(Integer, ForeignKey("bins.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

    bin = relationship("Bin", back_populates="photos")
