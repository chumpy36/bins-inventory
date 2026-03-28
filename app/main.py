import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import init_db
from app.routes import bins, items, categories, search, qr, photos


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Bin Inventory", lifespan=lifespan)

# Static files
STATIC_DIR = os.getenv("STATIC_DIR", "/app/app/static")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/photos", StaticFiles(directory=os.path.join(DATA_DIR, "photos")), name="photos")

# Routes
app.include_router(bins.router)
app.include_router(items.router)
app.include_router(categories.router)
app.include_router(search.router)
app.include_router(qr.router)
app.include_router(photos.router)
