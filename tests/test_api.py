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
    assert client.patch(f"/api/locations/{parent_id}", json={"parent_id": child_id}).status_code == 422
    grandchild = client.post("/api/locations", json={
        "name": "Guitar case", "kind": "case", "parent_id": child_id,
    })
    assert grandchild.status_code == 201
    hierarchy = client.get("/locations")
    assert hierarchy.status_code == 200
    assert all(name in hierarchy.text for name in ("Music room", "Guitar rack", "Guitar case"))
    detail = client.get(f"/locations/{grandchild.json()['id']}")
    assert detail.status_code == 200
    assert "Music room" in detail.text and "Guitar rack" in detail.text
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


def test_same_app_origin_and_redirect_validation():
    from app import cf_access
    from app.routes.suggest import _safe_next_url

    assert cf_access._same_app_origin("https://inventory.hollandit.work/path")
    assert not cf_access._same_app_origin("https://attacker.example/submit")
    assert not cf_access._same_app_origin("null")
    assert _safe_next_url("/locations", "/bin/token") == "/locations"
    assert _safe_next_url("//attacker.example", "/bin/token") == "/bin/token"
    assert _safe_next_url("/\\\\attacker.example", "/bin/token") == "/bin/token"


def test_migrations_are_idempotent(client):
    from app.database import init_db

    init_db()
    init_db()
    assert client.get("/api/gear").status_code == 200


def test_photo_reordering_is_scoped_to_its_record(client, monkeypatch):
    from fastapi.templating import Jinja2Templates

    from app.database import SessionLocal
    from app.models import Bin, InventoryItem, InventoryPhoto, Photo
    from app.routes import photos as photo_routes

    monkeypatch.setattr(
        photo_routes,
        "templates",
        Jinja2Templates(
            directory=str(Path(__file__).resolve().parents[1] / "app" / "templates")
        ),
    )

    with SessionLocal() as db:
        first_bin = Bin(name="First photo bin")
        second_bin = Bin(name="Second photo bin")
        gear = InventoryItem(name="Photo test guitar", item_type_id=1)
        db.add_all([first_bin, second_bin, gear])
        db.flush()

        bin_photos = [
            Photo(bin_id=first_bin.id, filename="bin-a.jpg", sort_order=0),
            Photo(bin_id=first_bin.id, filename="bin-b.jpg", sort_order=1),
            Photo(bin_id=second_bin.id, filename="other-bin.jpg", sort_order=0),
        ]
        gear_photos = [
            InventoryPhoto(inventory_item_id=gear.id, filename="gear-a.jpg", sort_order=0),
            InventoryPhoto(inventory_item_id=gear.id, filename="gear-b.jpg", sort_order=1),
            InventoryPhoto(inventory_item_id=gear.id, filename="gear-c.jpg", sort_order=2),
        ]
        db.add_all(bin_photos + gear_photos)
        db.commit()
        bin_b_id = bin_photos[1].id
        gear_c_id = gear_photos[2].id
        first_bin_id = first_bin.id
        second_bin_id = second_bin.id
        gear_id = gear.id

    assert client.post(f"/photo/{bin_b_id}/move/left").status_code == 200
    assert client.post(f"/photo/item/{gear_c_id}/move/left").status_code == 200
    assert client.post(f"/photo/item/{gear_c_id}/move/up").status_code == 400

    with SessionLocal() as db:
        first_bin_order = [
            p.filename for p in db.query(Photo)
            .filter(Photo.bin_id == first_bin_id)
            .order_by(Photo.sort_order, Photo.id)
        ]
        second_bin_order = [
            p.filename for p in db.query(Photo)
            .filter(Photo.bin_id == second_bin_id)
            .order_by(Photo.sort_order, Photo.id)
        ]
        gear_order = [
            p.filename for p in db.query(InventoryPhoto)
            .filter(InventoryPhoto.inventory_item_id == gear_id)
            .order_by(InventoryPhoto.sort_order, InventoryPhoto.id)
        ]

    assert first_bin_order == ["bin-b.jpg", "bin-a.jpg"]
    assert second_bin_order == ["other-bin.jpg"]
    assert gear_order == ["gear-a.jpg", "gear-c.jpg", "gear-b.jpg"]


def test_deep_and_cyclic_location_rendering(client):
    from types import SimpleNamespace
    from app.routes.locations import _tree

    locations = [SimpleNamespace(id=i, parent_id=i - 1 if i else None, name=str(i))
                 for i in range(1500)]
    rows = _tree(locations)
    assert [row['location'].id for row in rows] == list(range(1500))
    assert rows[-1]['depth'] == 1499
    locations[0].parent_id = 1499
    assert len(_tree(locations)) == 1500


@pytest.mark.parametrize('value', ['/\n/attacker.example', '/\t/attacker.example', '/path\r', '/path\x7f'])
def test_redirect_rejects_control_characters(client, value):
    from app.routes.suggest import _safe_next_url
    assert _safe_next_url(value, '/safe') == '/safe'


def test_authenticated_mutation_origin_policy(client, monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from app import cf_access

    monkeypatch.setattr(cf_access, 'TEAM_DOMAIN', 'test.cloudflareaccess.com')
    monkeypatch.setattr(cf_access, 'AUD', 'test-audience')
    monkeypatch.setattr(cf_access, 'EXPECTED_ORIGIN', 'https://inventory.hollandit.work')
    monkeypatch.setattr(cf_access.PyJWKClient, 'get_signing_key_from_jwt',
                        lambda *args: SimpleNamespace(key='test-key'))
    claims = {'email': 'test@example.com'}
    monkeypatch.setattr(cf_access.jwt, 'decode', lambda *args, **kwargs: claims)
    application = FastAPI()
    application.add_middleware(cf_access.CloudflareAccessMiddleware)

    @application.post('/mutate')
    async def mutate():
        return {'ok': True}

    with TestClient(application) as authenticated:
        headers = {'Cf-Access-Jwt-Assertion': 'test-token'}
        assert authenticated.post('/mutate').status_code == 403
        assert authenticated.post('/mutate', headers=headers).status_code == 403
        assert authenticated.post('/mutate', headers={**headers, 'Origin': 'https://attacker.example'}).status_code == 403
        assert authenticated.post('/mutate', headers={**headers, 'Origin': 'null', 'Referer': 'https://inventory.hollandit.work/'}).status_code == 403
        assert authenticated.post('/mutate', headers={**headers, 'Origin': 'https://inventory.hollandit.work'}).status_code == 200
        assert authenticated.post('/mutate', headers={**headers, 'Referer': 'https://inventory.hollandit.work/bin/test'}).status_code == 200
        claims.clear()
        claims['common_name'] = 'test-service'
        assert authenticated.post('/mutate', headers=headers).status_code == 200
        assert authenticated.post('/mutate', headers={**headers, 'Origin': 'https://attacker.example'}).status_code == 403


def test_photo_upload_limits_and_storage(client, monkeypatch):
    import io
    from PIL import Image
    from app.routes import photos

    assert Path(photos.PHOTOS_DIR) == Path(os.environ['DATA_DIR']) / 'photos'
    record = client.post('/api/bins', json={'name': 'Upload test'}).json()
    image_bytes = io.BytesIO()
    Image.new('RGB', (10, 10)).save(image_bytes, format='PNG')
    upload_url = f"/photo/upload/{record['token']}"
    files = {'file': ('test.png', image_bytes.getvalue(), 'image/png')}
    assert client.post(upload_url, files=files).status_code == 200
    before = set(Path(photos.PHOTOS_DIR).iterdir())
    assert len(before) == 1
    monkeypatch.setattr(photos, 'MAX_IMAGE_PIXELS', 50)
    response = client.post(upload_url, files=files)
    assert photos.IMAGE_TOO_LARGE_ERROR in response.text
    assert set(Path(photos.PHOTOS_DIR).iterdir()) == before
    monkeypatch.setattr(photos, 'MAX_UPLOAD_BYTES', 5)
    response = client.post(upload_url, files=files)
    assert photos.TOO_LARGE_ERROR in response.text
    assert set(Path(photos.PHOTOS_DIR).iterdir()) == before
