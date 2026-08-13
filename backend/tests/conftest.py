"""Keep the test run away from the real database.

`app.database` builds its engine at import time from DATABASE_URL, so this has
to be set before anything under `app` is imported — which is what a conftest at
the package root guarantees.
"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="pulse-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp}/test.db"
