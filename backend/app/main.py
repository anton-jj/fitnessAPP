from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pathlib import Path
from .database import init_db
from .config import settings
from .services.sync_manager import run_sync
from .services.auto_push import push_todays_workouts
from .routers import auth, dashboard, activities, wellness, sync, ai_coach, settings_router, weekly, trainer, profile
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.add_job(run_sync, "interval", minutes=settings.sync_interval, id="sync")
    scheduler.add_job(push_todays_workouts, "cron", hour=5, minute=0, id="auto_push")
    scheduler.start()
    log.info(f"Sync scheduled every {settings.sync_interval} minutes")
    log.info("Auto-push scheduled daily at 05:00")
    yield
    scheduler.shutdown()


app = FastAPI(title="Pulse", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(activities.router)
app.include_router(wellness.router)
app.include_router(sync.router)
app.include_router(ai_coach.router)
app.include_router(settings_router.router)
app.include_router(weekly.router)
app.include_router(trainer.router)
app.include_router(profile.router)

static_dir = Path(__file__).parent.parent.parent / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
