import secrets
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def generate_token():
    return secrets.token_urlsafe(6)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    color = Column(String, default="#6366f1")
    kind = Column(String, default="bin")
    created_at = Column(DateTime, default=utcnow)

    bins = relationship("Bin", back_populates="category", order_by="Bin.name")
    inventory_items = relationship("InventoryItem", back_populates="category")


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    kind = Column(String, default="other")
    parent_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    parent = relationship("Location", remote_side="Location.id", foreign_keys="Location.parent_id")
    bins = relationship("Bin", back_populates="location_obj")
    inventory_items = relationship("InventoryItem", back_populates="location")


class Bin(Base):
    __tablename__ = "bins"

    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, nullable=False, default=generate_token)
    name = Column(String, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    location = Column(String, nullable=True)  # legacy free-text; superseded by location_id
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    category = relationship("Category", back_populates="bins")
    location_obj = relationship("Location", back_populates="bins")
    items = relationship("Item", back_populates="bin", order_by="Item.name", cascade="all, delete-orphan")
    photos = relationship("Photo", back_populates="bin", order_by="Photo.sort_order", cascade="all, delete-orphan")

    @property
    def display_location(self):
        if self.location_obj:
            return self.location_obj.name
        return self.location or ""


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


class ItemType(Base):
    __tablename__ = "item_types"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    slug = Column(String, nullable=False, unique=True)
    icon = Column(String)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

    attribute_definitions = relationship(
        "AttributeDefinition", back_populates="item_type",
        order_by="AttributeDefinition.sort_order"
    )
    inventory_items = relationship("InventoryItem", back_populates="item_type")


class AttributeDefinition(Base):
    __tablename__ = "attribute_definitions"

    id = Column(Integer, primary_key=True)
    item_type_id = Column(Integer, ForeignKey("item_types.id", ondelete="CASCADE"), nullable=False)
    key = Column(String, nullable=False)
    label = Column(String, nullable=False)
    field_type = Column(String, default="text")  # text|textarea|integer|decimal|boolean|date|select|year
    options = Column(Text, nullable=True)         # JSON array string for 'select' type
    section = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)

    item_type = relationship("ItemType", back_populates="attribute_definitions")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True)
    item_type_id = Column(Integer, ForeignKey("item_types.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)

    name = Column(String, nullable=False)
    brand = Column(String, nullable=True)
    model = Column(String, nullable=True)
    year_produced = Column(Integer, nullable=True)
    color = Column(String, nullable=True)
    condition = Column(String, nullable=True)
    serial_number = Column(String, nullable=True)
    country_of_manufacture = Column(String, nullable=True)
    date_acquired = Column(String, nullable=True)
    acquired_from = Column(String, nullable=True)
    amount_paid = Column(Float, nullable=True)
    current_value = Column(Float, nullable=True)
    sold = Column(Integer, default=0)
    sale_price = Column(Float, nullable=True)
    date_sold = Column(String, nullable=True)
    rating = Column(Integer, nullable=True)
    story = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    token = Column(String, unique=True, nullable=False, default=generate_token)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    item_type = relationship("ItemType", back_populates="inventory_items")
    category = relationship("Category", back_populates="inventory_items")
    location = relationship("Location", back_populates="inventory_items")
    attributes = relationship(
        "ItemAttribute", back_populates="inventory_item",
        cascade="all, delete-orphan"
    )
    photos = relationship(
        "InventoryPhoto", back_populates="inventory_item",
        order_by="InventoryPhoto.sort_order", cascade="all, delete-orphan"
    )


class ItemAttribute(Base):
    __tablename__ = "item_attributes"

    id = Column(Integer, primary_key=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False)
    attribute_def_id = Column(Integer, ForeignKey("attribute_definitions.id", ondelete="CASCADE"), nullable=False)
    value = Column(Text, nullable=True)

    inventory_item = relationship("InventoryItem", back_populates="attributes")
    attribute_def = relationship("AttributeDefinition")


class InventoryPhoto(Base):
    __tablename__ = "inventory_photos"

    id = Column(Integer, primary_key=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

    inventory_item = relationship("InventoryItem", back_populates="photos")
