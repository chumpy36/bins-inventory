from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AttributeDefinition,
    Bin,
    Category,
    InventoryItem,
    Item,
    ItemAttribute,
    ItemType,
    Location,
)


router = APIRouter(prefix="/api", tags=["api"])


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NamedModel(APIModel):
    name: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class BinCreate(NamedModel):
    category_id: int | None = None
    location_id: int | None = None
    notes: str | None = None


class BinUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1)
    category_id: int | None = None
    location_id: int | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class ItemCreate(NamedModel):
    bin_id: int
    quantity: int = Field(default=1, ge=1)
    notes: str | None = None


class ItemUpdate(APIModel):
    bin_id: int | None = None
    name: str | None = Field(default=None, min_length=1)
    quantity: int | None = Field(default=None, ge=1)
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class LocationCreate(NamedModel):
    kind: str = "other"
    parent_id: int | None = None
    notes: str | None = None


class LocationUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1)
    kind: str | None = None
    parent_id: int | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class GearCreate(NamedModel):
    item_type_slug: str
    category_id: int | None = None
    location_id: int | None = None
    brand: str | None = None
    model: str | None = None
    year_produced: int | None = None
    color: str | None = None
    condition: str | None = None
    serial_number: str | None = None
    country_of_manufacture: str | None = None
    date_acquired: str | None = None
    acquired_from: str | None = None
    amount_paid: float | None = None
    current_value: float | None = None
    sold: bool = False
    sale_price: float | None = None
    date_sold: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    story: str | None = None
    notes: str | None = None
    attributes: dict[str, str | None] = Field(default_factory=dict)


class GearUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1)
    category_id: int | None = None
    location_id: int | None = None
    brand: str | None = None
    model: str | None = None
    year_produced: int | None = None
    color: str | None = None
    condition: str | None = None
    serial_number: str | None = None
    country_of_manufacture: str | None = None
    date_acquired: str | None = None
    acquired_from: str | None = None
    amount_paid: float | None = None
    current_value: float | None = None
    sold: bool | None = None
    sale_price: float | None = None
    date_sold: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    story: str | None = None
    notes: str | None = None
    attributes: dict[str, str | None] | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


def _creator(request: Request) -> str | None:
    return getattr(request.state, "user_email", "") or None


def _clean_optional(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _require(db: Session, model, object_id: int, label: str):
    obj = db.get(model, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _validate_refs(
    db: Session,
    *,
    category_id: int | None = None,
    location_id: int | None = None,
    bin_id: int | None = None,
) -> None:
    if category_id is not None:
        _require(db, Category, category_id, "Category")
    if location_id is not None:
        _require(db, Location, location_id, "Location")
    if bin_id is not None:
        _require(db, Bin, bin_id, "Bin")


def _bin_json(obj: Bin) -> dict[str, Any]:
    return {
        "id": obj.id, "token": obj.token, "name": obj.name,
        "category_id": obj.category_id, "location_id": obj.location_id,
        "notes": obj.notes, "created_by": obj.created_by,
        "created_at": obj.created_at, "updated_at": obj.updated_at,
    }


def _item_json(obj: Item) -> dict[str, Any]:
    return {
        "id": obj.id, "bin_id": obj.bin_id, "name": obj.name,
        "quantity": obj.quantity, "notes": obj.notes,
        "created_by": obj.created_by, "created_at": obj.created_at,
    }


def _location_json(obj: Location) -> dict[str, Any]:
    return {
        "id": obj.id, "name": obj.name, "kind": obj.kind,
        "parent_id": obj.parent_id, "notes": obj.notes,
        "created_by": obj.created_by, "created_at": obj.created_at,
    }


def _gear_json(obj: InventoryItem) -> dict[str, Any]:
    return {
        "id": obj.id, "token": obj.token,
        "item_type": {"id": obj.item_type.id, "slug": obj.item_type.slug, "name": obj.item_type.name},
        "category_id": obj.category_id, "location_id": obj.location_id,
        "name": obj.name, "brand": obj.brand, "model": obj.model,
        "year_produced": obj.year_produced, "color": obj.color,
        "condition": obj.condition, "serial_number": obj.serial_number,
        "country_of_manufacture": obj.country_of_manufacture,
        "date_acquired": obj.date_acquired, "acquired_from": obj.acquired_from,
        "amount_paid": obj.amount_paid, "current_value": obj.current_value,
        "sold": bool(obj.sold), "sale_price": obj.sale_price,
        "date_sold": obj.date_sold, "rating": obj.rating,
        "story": obj.story, "notes": obj.notes,
        "attributes": {a.attribute_def.key: a.value for a in obj.attributes},
        "created_by": obj.created_by, "created_at": obj.created_at,
        "updated_at": obj.updated_at,
    }


def _apply(obj: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        setattr(obj, key, _clean_optional(value))


def _set_attributes(db: Session, item: InventoryItem, values: dict[str, str | None]) -> None:
    definitions = {
        definition.key: definition
        for definition in db.query(AttributeDefinition).filter(
            AttributeDefinition.item_type_id == item.item_type_id
        )
    }
    unknown = sorted(set(values) - set(definitions))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"message": "Unknown attributes for item type", "keys": unknown},
        )
    existing = {attribute.attribute_def_id: attribute for attribute in item.attributes}
    for key, value in values.items():
        definition = definitions[key]
        attribute = existing.get(definition.id)
        cleaned = _clean_optional(value)
        if cleaned is None:
            if attribute is not None:
                db.delete(attribute)
        elif attribute is None:
            db.add(ItemAttribute(
                inventory_item_id=item.id,
                attribute_def_id=definition.id,
                value=cleaned,
            ))
        else:
            attribute.value = cleaned


@router.get("/bins")
def list_bins(db: Session = Depends(get_db)):
    return [_bin_json(obj) for obj in db.query(Bin).order_by(Bin.id).all()]


@router.post("/bins", status_code=status.HTTP_201_CREATED)
def create_bin(payload: BinCreate, request: Request, db: Session = Depends(get_db)):
    _validate_refs(db, category_id=payload.category_id, location_id=payload.location_id)
    obj = Bin(**{key: _clean_optional(value) for key, value in payload.model_dump().items()}, created_by=_creator(request))
    db.add(obj); db.commit(); db.refresh(obj)
    return _bin_json(obj)


@router.get("/bins/{object_id}")
def get_bin(object_id: int, db: Session = Depends(get_db)):
    return _bin_json(_require(db, Bin, object_id, "Bin"))


@router.patch("/bins/{object_id}")
def update_bin(object_id: int, payload: BinUpdate, db: Session = Depends(get_db)):
    obj = _require(db, Bin, object_id, "Bin")
    values = payload.model_dump(exclude_unset=True)
    _validate_refs(db, category_id=values.get("category_id"), location_id=values.get("location_id"))
    if "location_id" in values:
        obj.location = None
    _apply(obj, values); db.commit(); db.refresh(obj)
    return _bin_json(obj)


@router.get("/items")
def list_items(db: Session = Depends(get_db)):
    return [_item_json(obj) for obj in db.query(Item).order_by(Item.id).all()]


@router.post("/items", status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, request: Request, db: Session = Depends(get_db)):
    _validate_refs(db, bin_id=payload.bin_id)
    obj = Item(**{key: _clean_optional(value) for key, value in payload.model_dump().items()}, created_by=_creator(request))
    db.add(obj); db.commit(); db.refresh(obj)
    return _item_json(obj)


@router.get("/items/{object_id}")
def get_item(object_id: int, db: Session = Depends(get_db)):
    return _item_json(_require(db, Item, object_id, "Item"))


@router.patch("/items/{object_id}")
def update_item(object_id: int, payload: ItemUpdate, db: Session = Depends(get_db)):
    obj = _require(db, Item, object_id, "Item")
    values = payload.model_dump(exclude_unset=True)
    _validate_refs(db, bin_id=values.get("bin_id"))
    _apply(obj, values); db.commit(); db.refresh(obj)
    return _item_json(obj)


@router.get("/locations")
def list_locations(db: Session = Depends(get_db)):
    return [_location_json(obj) for obj in db.query(Location).order_by(Location.id).all()]


@router.post("/locations", status_code=status.HTTP_201_CREATED)
def create_location(payload: LocationCreate, request: Request, db: Session = Depends(get_db)):
    if payload.parent_id is not None:
        _require(db, Location, payload.parent_id, "Parent location")
    obj = Location(**{key: _clean_optional(value) for key, value in payload.model_dump().items()}, created_by=_creator(request))
    db.add(obj); db.commit(); db.refresh(obj)
    return _location_json(obj)


@router.get("/locations/{object_id}")
def get_location(object_id: int, db: Session = Depends(get_db)):
    return _location_json(_require(db, Location, object_id, "Location"))


@router.patch("/locations/{object_id}")
def update_location(object_id: int, payload: LocationUpdate, db: Session = Depends(get_db)):
    obj = _require(db, Location, object_id, "Location")
    values = payload.model_dump(exclude_unset=True)
    parent_id = values.get("parent_id")
    if parent_id == object_id:
        raise HTTPException(status_code=422, detail="A location cannot be its own parent")
    if parent_id is not None:
        _require(db, Location, parent_id, "Parent location")
    _apply(obj, values); db.commit(); db.refresh(obj)
    return _location_json(obj)


@router.get("/gear")
def list_gear(db: Session = Depends(get_db)):
    return [_gear_json(obj) for obj in db.query(InventoryItem).order_by(InventoryItem.id).all()]


@router.post("/gear", status_code=status.HTTP_201_CREATED)
def create_gear(payload: GearCreate, request: Request, db: Session = Depends(get_db)):
    item_type = db.query(ItemType).filter(ItemType.slug == payload.item_type_slug).first()
    if item_type is None:
        raise HTTPException(status_code=404, detail="Item type not found")
    values = payload.model_dump(exclude={"item_type_slug", "attributes"})
    _validate_refs(db, category_id=payload.category_id, location_id=payload.location_id)
    obj = InventoryItem(
        item_type_id=item_type.id,
        **{key: _clean_optional(value) for key, value in values.items()},
        created_by=_creator(request),
    )
    db.add(obj); db.flush(); _set_attributes(db, obj, payload.attributes)
    db.commit(); db.refresh(obj)
    return _gear_json(obj)


@router.get("/gear/{object_id}")
def get_gear(object_id: int, db: Session = Depends(get_db)):
    return _gear_json(_require(db, InventoryItem, object_id, "Gear item"))


@router.patch("/gear/{object_id}")
def update_gear(object_id: int, payload: GearUpdate, db: Session = Depends(get_db)):
    obj = _require(db, InventoryItem, object_id, "Gear item")
    values = payload.model_dump(exclude_unset=True)
    attributes = values.pop("attributes", None)
    _validate_refs(db, category_id=values.get("category_id"), location_id=values.get("location_id"))
    _apply(obj, values)
    if attributes is not None:
        _set_attributes(db, obj, attributes)
    db.commit(); db.refresh(obj)
    return _gear_json(obj)
