import os
import tempfile
from pathlib import Path

import pytest

TEST_ROOT = Path(tempfile.mkdtemp(prefix="attendance-tests-"))
os.environ.setdefault("APP_DB_PATH", str(TEST_ROOT / "attendance.db"))
os.environ.setdefault("APP_SECRET_KEY", "test-secret")
os.environ.setdefault("DEFAULT_ADMIN_USERNAME", "admin")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "Admin@123")
os.environ.setdefault("DEFAULT_ADMIN_FULL_NAME", "System Admin")

import web  # noqa: E402


@pytest.fixture()
def client():
    web.app.config.update(TESTING=True)

    with web.app.app_context():
        db = web.get_db()
        db.execute("DELETE FROM attendance_records")
        db.execute("DELETE FROM face_profiles")
        db.execute("DELETE FROM subjects")
        db.execute("DELETE FROM students")
        db.execute("DELETE FROM user_permissions")
        default_admin = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
        db.execute("DELETE FROM users WHERE username != ?", (default_admin,))
        db.commit()

    with web.app.test_client() as test_client:
        yield test_client
