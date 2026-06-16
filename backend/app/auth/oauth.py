"""
Google OAuth client (Authlib). `oauth` is None when Google credentials are not
configured, so the rest of the app degrades gracefully (the /google endpoints
return 503 instead of crashing at import).
"""
from __future__ import annotations

from ..config import settings

oauth = None

if settings.google_client_id and settings.google_client_secret:
    from authlib.integrations.starlette_client import OAuth

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
