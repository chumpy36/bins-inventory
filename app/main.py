import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.cf_access import CloudflareAccessMiddleware
from app.database import init_db
from app.routes import api, bins, items, categories, search, qr, photos, inventory, locations, suggest


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Home Inventory", lifespan=lifespan)
app.add_middleware(CloudflareAccessMiddleware)

APP_DIR = os.path.dirname(__file__)
STATIC_DIR = os.getenv("STATIC_DIR", os.path.join(APP_DIR, "static"))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(APP_DIR), "data"))

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/photos", StaticFiles(directory=os.path.join(DATA_DIR, "photos")), name="photos")

app.include_router(api.router)
app.include_router(bins.router)
app.include_router(items.router)
app.include_router(categories.router)
app.include_router(search.router)
app.include_router(qr.router)
app.include_router(photos.router)
app.include_router(inventory.router)
app.include_router(locations.router)
app.include_router(suggest.router)
app.include_router(suggest.review_router)
