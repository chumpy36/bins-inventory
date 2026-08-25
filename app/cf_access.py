"""Validate the Cloudflare Access JWT at the origin.

Defense-in-depth: the app is only reachable through the Cloudflare tunnel,
but if the Access policy is ever deleted or the hostname re-routed, this
middleware keeps every request 403 unless it carries a JWT signed by our
Access team. Configured via CF_ACCESS_TEAM_DOMAIN + CF_ACCESS_AUD; if
either is unset (local dev), validation is skipped.
"""
import os

import jwt
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

TEAM_DOMAIN = os.getenv("CF_ACCESS_TEAM_DOMAIN", "")  # e.g. hitga.cloudflareaccess.com
AUD = os.getenv("CF_ACCESS_AUD", "")


class CloudflareAccessMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._jwks = (
            PyJWKClient(f"https://{TEAM_DOMAIN}/cdn-cgi/access/certs", cache_keys=True)
            if TEAM_DOMAIN and AUD
            else None
        )

    async def dispatch(self, request, call_next):
        if self._jwks is None:
            return await call_next(request)

        token = request.headers.get("Cf-Access-Jwt-Assertion", "")
        if not token:
            return PlainTextResponse("Forbidden: missing Cloudflare Access token", status_code=403)

        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], audience=AUD)
        except Exception:
            return PlainTextResponse("Forbidden: invalid Cloudflare Access token", status_code=403)

        # Human sessions carry email; service-token sessions carry common_name
        # (the service token client ID) instead.
        request.state.user_email = claims.get("email") or claims.get("common_name", "")
        return await call_next(request)
