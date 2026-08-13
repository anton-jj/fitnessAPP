from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pathlib import Path
import re
from .database import init_db
from .config import settings
from .services.sync_manager import run_sync
from .services.auto_push import push_todays_workouts
from .services import session_auth
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
    if session_auth.is_enabled():
        log.info("PIN authentication enabled")
    else:
        log.warning(
            "APP_PIN is unset — every endpoint is open to anyone who can reach "
            "this port. Set APP_PIN, and do not expose this app to the internet."
        )
    yield
    scheduler.shutdown()


app = FastAPI(title="Pulse", version="1.0.0", lifespan=lifespan)

# Endpoints that must work without a session:
#   health   — container healthchecks run before anyone logs in
#   auth     — the login flow itself, and the Strava OAuth redirect, which
#              arrives from Strava's servers with no cookie of ours
#   .ics     — calendar apps cannot log in; guarded by a key in the URL instead
_OPEN_PATHS = {
    "/api/health",
    "/api/auth/session",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/strava",
    "/api/auth/strava/callback",
}
_OPEN_PATTERNS = [re.compile(r"^/api/ai/plan/\d+/calendar\.ics$")]


def _is_open(path: str) -> bool:
    return path in _OPEN_PATHS or any(p.match(path) for p in _OPEN_PATTERNS)


@app.middleware("http")
async def require_session(request: Request, call_next):
    """Gate the API behind the PIN session.

    Only /api is gated. The static bundle stays public so the browser can load
    the app far enough to show the login screen.
    """
    path = request.url.path
    if (
        session_auth.is_enabled()
        and path.startswith("/api")
        and request.method != "OPTIONS"
        and not _is_open(path)
        and not session_auth.verify_token(request.cookies.get(session_auth.COOKIE_NAME))
    ):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return await call_next(request)


# The app and its API are served from one origin, so no cross-origin request is
# expected. Anything listed here is opt-in via APP_CORS_ORIGINS.
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
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
