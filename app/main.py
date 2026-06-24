import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .routers import actions, api, dashboard, garden, settings as settings_router
from .scheduler import create_scheduler

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Ogrodnik AI - POC")

app.include_router(dashboard.router)
app.include_router(actions.router)
app.include_router(api.router)
app.include_router(garden.router)
app.include_router(settings_router.router)

app.mount("/photos", StaticFiles(directory=str(settings.photos_dir)), name="photos")
app.mount("/maps", StaticFiles(directory=str(settings.maps_dir)), name="maps")

scheduler = create_scheduler()


@app.on_event("startup")
async def on_startup():
    init_db()
    scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    scheduler.shutdown()


@app.get("/health")
def health():
    """Prosty endpoint dla Docker HEALTHCHECK / load balancera."""
    return {"status": "ok"}
