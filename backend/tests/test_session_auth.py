import time

import pytest

from app.config import settings
from app.services import session_auth


@pytest.fixture(autouse=True)
def clean_auth():
    """Each test gets a known PIN, a fixed secret, and no carried-over lockout."""
    original_pin = settings.app_pin
    original_secret = settings.app_secret_key
    settings.app_pin = "4821"
    settings.app_secret_key = "test-secret-key"
    session_auth.reset_throttle()
    yield
    settings.app_pin = original_pin
    settings.app_secret_key = original_secret
    session_auth.reset_throttle()


# --- Tokens ---

def test_a_freshly_issued_token_verifies():
    assert session_auth.verify_token(session_auth.issue_token())


def test_nothing_verifies_without_a_token():
    for value in (None, "", "garbage", "v1", "v1.abc.def"):
        assert not session_auth.verify_token(value), value


def test_an_expired_token_is_rejected():
    past = time.time() - session_auth.SESSION_DAYS * 86400 - 10
    assert not session_auth.verify_token(session_auth.issue_token(now=past))


def test_a_token_cannot_be_extended_by_editing_its_expiry():
    """The expiry is signed, so moving it invalidates the signature."""
    token = session_auth.issue_token()
    _, expiry, signature = token.split(".", 2)
    forged = f"v1.{int(expiry) + 86400}.{signature}"
    assert not session_auth.verify_token(forged)


def test_a_token_signed_with_another_secret_is_rejected():
    token = session_auth.issue_token()
    settings.app_secret_key = "a-different-secret"
    assert not session_auth.verify_token(token)


def test_changing_the_secret_signs_everyone_out():
    settings.app_secret_key = "secret-one"
    token = session_auth.issue_token()
    settings.app_secret_key = "secret-two"
    assert not session_auth.verify_token(token)


# --- PIN checking and lockout ---

def test_the_right_pin_passes_and_a_wrong_one_does_not():
    assert session_auth.check_pin("4821", "1.2.3.4")
    assert not session_auth.check_pin("0000", "1.2.3.4")


def test_an_empty_pin_never_passes():
    for value in ("", None):
        assert not session_auth.check_pin(value, "1.2.3.4")


def test_repeated_failures_lock_the_client_out():
    for _ in range(session_auth.MAX_ATTEMPTS):
        session_auth.check_pin("0000", "1.2.3.4")
    assert session_auth.seconds_until_unlocked("1.2.3.4") > 0


def test_the_lockout_is_per_client():
    for _ in range(session_auth.MAX_ATTEMPTS):
        session_auth.check_pin("0000", "1.2.3.4")
    assert session_auth.seconds_until_unlocked("5.6.7.8") == 0


def test_a_correct_pin_clears_the_failure_count():
    for _ in range(session_auth.MAX_ATTEMPTS - 1):
        session_auth.check_pin("0000", "1.2.3.4")
    assert session_auth.check_pin("4821", "1.2.3.4")
    assert session_auth.seconds_until_unlocked("1.2.3.4") == 0


def test_old_failures_fall_out_of_the_window():
    stale = time.time() - session_auth.ATTEMPT_WINDOW - 1
    for _ in range(session_auth.MAX_ATTEMPTS):
        session_auth.check_pin("0000", "1.2.3.4", now=stale)
    assert session_auth.seconds_until_unlocked("1.2.3.4") == 0


def test_the_lockout_expires():
    start = time.time()
    for _ in range(session_auth.MAX_ATTEMPTS):
        session_auth.check_pin("0000", "1.2.3.4", now=start)
    later = start + session_auth.LOCKOUT_SECONDS + 1
    assert session_auth.seconds_until_unlocked("1.2.3.4", now=later) == 0


# --- Enablement ---

def test_auth_is_off_without_a_pin():
    settings.app_pin = ""
    assert not session_auth.is_enabled()


def test_auth_is_on_with_a_pin():
    assert session_auth.is_enabled()


# --- Calendar feed keys ---

def test_a_feed_key_is_stable_for_a_plan():
    assert session_auth.feed_key(7) == session_auth.feed_key(7)


def test_feed_keys_differ_between_plans():
    assert session_auth.feed_key(7) != session_auth.feed_key(8)


def test_a_feed_needs_its_key_once_a_pin_is_set():
    assert session_auth.verify_feed_key(7, session_auth.feed_key(7))
    assert not session_auth.verify_feed_key(7, None)
    assert not session_auth.verify_feed_key(7, "wrong")
    # Counting upward from another plan's key must not work either.
    assert not session_auth.verify_feed_key(7, session_auth.feed_key(8))


def test_feeds_stay_open_when_auth_is_off():
    settings.app_pin = ""
    assert session_auth.verify_feed_key(7, None)
