"""The gate itself: what a request can reach with and without a session.

These go through the real ASGI app rather than calling the helpers directly,
because the thing worth proving is that the middleware is actually wired to
every route — not that HMAC works.
"""
import asyncio

import httpx
import pytest

from app.config import settings
from app.database import init_db
from app.main import app
from app.services import session_auth


@pytest.fixture(autouse=True)
def pin_set():
    original_pin = settings.app_pin
    original_secret = settings.app_secret_key
    settings.app_pin = "4821"
    settings.app_secret_key = "test-secret-key"
    session_auth.reset_throttle()
    yield
    settings.app_pin = original_pin
    settings.app_secret_key = original_secret
    session_auth.reset_throttle()


def call(fn):
    """Run one coroutine against the app, with the schema in place."""
    async def runner():
        await init_db()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://test") as client:
            return await fn(client)
    return asyncio.run(runner())


GUARDED = [
    "/api/profile",
    "/api/dashboard",
    "/api/activities",
    "/api/ai/plan",
    "/api/settings",
    "/api/sync/status",
    "/api/wellness",
]


def test_guarded_endpoints_refuse_an_anonymous_request():
    async def go(client):
        return {path: (await client.get(path)).status_code for path in GUARDED}

    for path, status in call(go).items():
        assert status == 401, f"{path} returned {status}, expected 401"


def test_writes_are_refused_too():
    """A read-only gate would still let someone wipe the profile."""
    async def go(client):
        return await client.put("/api/profile", json={"weekly_hours": 99})

    assert call(go).status_code == 401


def test_health_stays_open_for_container_checks():
    async def go(client):
        return await client.get("/api/health")

    assert call(go).status_code == 200


def test_logging_in_with_the_right_pin_opens_the_api():
    async def go(client):
        login = await client.post("/api/auth/login", json={"pin": "4821"})
        profile = await client.get("/api/profile")
        return login, profile

    login, profile = call(go)
    assert login.status_code == 200
    assert session_auth.COOKIE_NAME in login.cookies
    assert profile.status_code == 200


def test_the_session_cookie_is_httponly():
    """JavaScript must not be able to read it."""
    async def go(client):
        return await client.post("/api/auth/login", json={"pin": "4821"})

    header = call(go).headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=lax" in header


def test_the_wrong_pin_is_refused():
    async def go(client):
        response = await client.post("/api/auth/login", json={"pin": "0000"})
        profile = await client.get("/api/profile")
        return response, profile

    response, profile = call(go)
    assert response.status_code == 401
    assert profile.status_code == 401


def test_guessing_gets_locked_out():
    async def go(client):
        for _ in range(session_auth.MAX_ATTEMPTS):
            await client.post("/api/auth/login", json={"pin": "0000"})
        # Even the correct PIN has to wait once the lockout is in force.
        return await client.post("/api/auth/login", json={"pin": "4821"})

    assert call(go).status_code == 429


def test_a_forged_cookie_does_not_get_in():
    async def go(client):
        client.cookies.set(session_auth.COOKIE_NAME, "v1.99999999999.deadbeef")
        return await client.get("/api/profile")

    assert call(go).status_code == 401


def test_logging_out_ends_the_session():
    async def go(client):
        await client.post("/api/auth/login", json={"pin": "4821"})
        await client.post("/api/auth/logout")
        return await client.get("/api/profile")

    assert call(go).status_code == 401


def test_session_status_reports_whether_a_pin_is_needed():
    async def go(client):
        anon = await client.get("/api/auth/session")
        await client.post("/api/auth/login", json={"pin": "4821"})
        signed_in = await client.get("/api/auth/session")
        return anon.json(), signed_in.json()

    anon, signed_in = call(go)
    assert anon == {"required": True, "authenticated": False}
    assert signed_in == {"required": True, "authenticated": True}


def test_the_calendar_feed_needs_its_key_but_not_a_session():
    async def go(client):
        without = await client.get("/api/ai/plan/1/calendar.ics")
        wrong = await client.get("/api/ai/plan/1/calendar.ics?key=nope")
        return without, wrong

    without, wrong = call(go)
    # 404 rather than 401: an anonymous caller learns nothing about what exists.
    assert without.status_code == 404
    assert wrong.status_code == 404


def test_nothing_is_gated_when_no_pin_is_set():
    settings.app_pin = ""

    async def go(client):
        return await client.get("/api/profile")

    assert call(go).status_code == 200
