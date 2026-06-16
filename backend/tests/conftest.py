"""
Test configuration. Sets a throwaway database + deterministic auth settings
BEFORE the application package is imported, so the module-level SQLAlchemy
engine binds to the temp DB instead of the real one.
"""
import os
import tempfile

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="arca-test-"), "test.db")

os.environ["DB_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "adminpass123"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["COOKIE_SECURE"] = "false"
