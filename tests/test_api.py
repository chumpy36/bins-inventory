import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("inventory-api")
    (data_dir / "photos").mkdir()
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["DATABASE_URL"] = f"sqlite:///{data_dir / 'bins.db'}"
    os.environ.pop("CF_ACCESS_TEAM_DOMAIN", None)
    os.environ.pop("CF_ACCESS_AUD", None)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    application = importlib.import_module("app.main").app

    class TestIdentityMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user_email = "api-test@hollandit.work"
            return await call_next(request)

    application.add_middleware(TestIdentityMiddleware)
    with TestClient(application) as test_client:
        yield test_client


def test_bin_and_item_crud(client):
    response = client.post("/api/bins", json={"name": "Studio bin"})
    assert response.status_code == 201
    bin_record = response.json()
    assert bin_record["created_by"] == "api-test@hollandit.work"

    response = client.post("/api/items", json={
        "bin_id": bin_record["id"], "name": "Patch cables", "quantity": 3,
    })
    assert response.status_code == 201
    item = response.json()
    assert item["created_by"] == "api-test@hollandit.work"

    response = client.patch(f"/api/items/{item['id']}", json={"quantity": 4})
    assert response.status_code == 200
    assert response.json()["quantity"] == 4
    assert client.get(f"/api/bins/{bin_record['id']}").status_code == 200
    assert len(client.get("/api/items").json()) == 1


def test_location_crud_and_reference_validation(client):
    parent = client.post("/api/locations", json={"name": "Music room", "kind": "room"})
    assert parent.status_code == 201
    parent_id = parent.json()["id"]

    child = client.post("/api/locations", json={
        "name": "Guitar rack", "kind": "rack", "parent_id": parent_id,
    })
    assert child.status_code == 201
    child_id = child.json()["id"]
    assert client.patch(f"/api/locations/{child_id}", json={"notes": "East wall"}).json()["notes"] == "East wall"
    assert client.patch(f"/api/locations/{child_id}", json={"parent_id": child_id}).status_code == 422
    assert client.post("/api/bins", json={"name": "Bad location", "location_id": 99999}).status_code == 404


def test_gear_crud_with_structured_attributes(client):
    response = client.post("/api/gear", json={
        "item_type_slug": "guitar",
        "name": "SG",
        "brand": "Gibson",
        "attributes": {
            "setup_neck_relief": ".008 in",
            "setup_action_low_e": "4/64 in",
        },
    })
    assert response.status_code == 201
    gear = response.json()
    assert gear["created_by"] == "api-test@hollandit.work"
    assert gear["attributes"]["setup_neck_relief"] == ".008 in"

    response = client.patch(f"/api/gear/{gear['id']}", json={
        "notes": "Setup checked",
        "attributes": {
            "setup_action_low_e": "5/64 in",
            "setup_neck_relief": None,
        },
    })
    assert response.status_code == 200
    updated = response.json()
    assert updated["notes"] == "Setup checked"
    assert updated["attributes"]["setup_action_low_e"] == "5/64 in"
    assert "setup_neck_relief" not in updated["attributes"]
    assert client.get(f"/api/gear/{gear['id']}").status_code == 200
    assert len(client.get("/api/gear").json()) == 1


def test_validation_errors_are_safe(client):
    assert client.post("/api/items", json={"bin_id": 99999, "name": "No bin"}).status_code == 404
    assert client.post("/api/bins", json={"name": "   "}).status_code == 422
    assert client.patch("/api/gear/99999", json={"name": "Missing"}).status_code == 404

    gear = client.get("/api/gear").json()[0]
    response = client.patch(f"/api/gear/{gear['id']}", json={
        "attributes": {"not_a_real_field": "value"},
    })
    assert response.status_code == 422


def test_migrations_are_idempotent(client):
    from app.database import init_db

    init_db()
    init_db()
    assert client.get("/api/gear").status_code == 200
