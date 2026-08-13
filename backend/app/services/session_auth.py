"""PIN authentication for a single-user, self-hosted instance.

Deliberately small: one PIN, a signed cookie, and a lockout so the PIN cannot
be guessed. There are no accounts because there is only ever one athlete.

Auth is off when APP_PIN is unset, which keeps local development and first-run
setup friction-free. Anything reachable beyond localhost should set it — the
app has no other access control, and every endpoint reads or writes the
athlete's data.
"""
import hashlib
import hmac
import logging
import secrets
import time

from ..config import settings

log = logging.getLogger(__name__)

COOKIE_NAME = "pulse_session"
SESSION_DAYS = 30

# A PIN is short enough to brute force in seconds if we let it be tried freely.
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900  # 15 minutes
ATTEMPT_WINDOW = 900

# Failed attempts per client, trimmed to the window on each check. In-memory is
# the right scope: one process, one user, and a restart clearing a lockout is
# not a weakness worth a database table for.
_failures: dict[str, list[float]] = {}


def _secret() -> bytes:
    """Signing key. A per-process random key when none was configured.

    Falling back to the shipped default would mean every deployment signs
    cookies with a key that is public in the repository, so an unset key gets a
    random one instead — sessions then end at restart, which is the safe way to
    be wrong.
    """
    configured = settings.app_secret_key
    if configured and configured != "change-me":
        return configured.encode()
    global _ephemeral_secret
    try:
        return _ephemeral_secret
    except NameError:
        _ephemeral_secret = secrets.token_bytes(32)
        if is_enabled():
            log.warning(
                "APP_SECRET_KEY is unset — using a random key. Sessions will "
                "end whenever the app restarts. Set APP_SECRET_KEY to keep them."
            )
        return _ephemeral_secret


def is_enabled() -> bool:
    return bool(settings.app_pin)


def _sign(expires_at: int) -> str:
    return hmac.new(_secret(), str(expires_at).encode(), hashlib.sha256).hexdigest()


def issue_token(now: float | None = None) -> str:
    expires_at = int((now or time.time()) + SESSION_DAYS * 86400)
    return f"v1.{expires_at}.{_sign(expires_at)}"


def verify_token(token: str | None, now: float | None = None) -> bool:
    if not token:
        return False
    try:
        version, raw_expiry, signature = token.split(".", 2)
        expires_at = int(raw_expiry)
    except (ValueError, AttributeError):
        return False
    if version != "v1":
        return False
    # Compare before the expiry check so a forged token cannot be distinguished
    # from an expired one by how long the request takes.
    valid = hmac.compare_digest(signature, _sign(expires_at))
    return valid and expires_at > (now or time.time())


def _recent_failures(client: str, now: float) -> list[float]:
    attempts = [t for t in _failures.get(client, []) if now - t < ATTEMPT_WINDOW]
    if attempts:
        _failures[client] = attempts
    else:
        _failures.pop(client, None)
    return attempts


def seconds_until_unlocked(client: str, now: float | None = None) -> int:
    """How long this client must wait, or 0 if it may try now."""
    now = now or time.time()
    attempts = _recent_failures(client, now)
    if len(attempts) < MAX_ATTEMPTS:
        return 0
    unlocks_at = attempts[-1] + LOCKOUT_SECONDS
    return max(0, int(unlocks_at - now))


def check_pin(candidate: str, client: str, now: float | None = None) -> bool:
    """Verify a PIN, recording the attempt against this client's lockout."""
    now = now or time.time()
    ok = hmac.compare_digest(str(candidate or ""), settings.app_pin)
    if ok:
        _failures.pop(client, None)
    else:
        _failures.setdefault(client, []).append(now)
    return ok


def reset_throttle() -> None:
    """Clear every lockout. For tests."""
    _failures.clear()


def feed_key(plan_id: int) -> str:
    """Unguessable key for a calendar feed URL.

    Calendar apps cannot log in, so the feed stays outside the session check.
    A bare plan id would leave it open to anyone who counts upward from 1, so
    the URL carries a key derived from the signing secret instead.
    """
    return hmac.new(_secret(), f"feed:{plan_id}".encode(), hashlib.sha256).hexdigest()[:32]


def verify_feed_key(plan_id: int, key: str | None) -> bool:
    if not is_enabled():
        return True
    return bool(key) and hmac.compare_digest(key, feed_key(plan_id))
