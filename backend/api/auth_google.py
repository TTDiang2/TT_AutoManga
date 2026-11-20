"""Sign in with Google (OpenID Connect, authorization code + PKCE).

``GET /api/auth/google/start?next=/path`` sends the browser to Google;
``GET /api/auth/google/callback`` exchanges the code, checks the ID token's
claims and sets the usual ``am_session`` cookie (with ``email``). Both are
public (the gate lets them through). The per-attempt state (state, nonce,
PKCE verifier, next) travels in a signed, HttpOnly ``am_oauth`` cookie, not
in server memory, so a restart mid-login is harmless.

Setup: docs/GOOGLE_LOGIN.md. Config: the client id/secret in data/auth.json
(``python -m backend.core.auth set-google``), ``settings.auth.publicUrl``
and ``settings.auth.googleAllowedEmails``.

The ID token comes straight from Google's token endpoint over TLS, so its
signature is not checked (OIDC Core 3.1.3.7, point 6); its claims are."""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import List, Optional
from urllib.parse import quote, urlencode, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..core import auth, config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/google", tags=["auth"])

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
CALLBACK_PATH = "/api/auth/google/callback"

OAUTH_COOKIE = "am_oauth"
OAUTH_COOKIE_PATH = "/api/auth/google"
OAUTH_MAX_AGE = 600
CLOCK_SKEW_S = 120
MAX_EMAILS = 50

PUBLIC_PATHS = {
    ("GET", "/api/auth/google/start"),
    ("GET", CALLBACK_PATH),
}


def _client() -> httpx.AsyncClient:
    """The HTTP client for the token request (tests replace this)."""
    return httpx.AsyncClient(timeout=15.0)


def redirect_uri() -> str:
    return auth.public_url() + CALLBACK_PATH


def safe_next(value: Optional[str]) -> str:
    """A same-site relative path to return to, else "/". Refuses anything a
    browser could read as another origin: "//host", "/\\host", schemes,
    control characters."""
    if not value or not isinstance(value, str) or len(value) > 1024:
        return "/"
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    if any(ord(c) < 0x21 or ord(c) == 0x7f for c in value):
        return "/"
    try:
        parts = urlsplit(value)
    except ValueError:
        return "/"
    if parts.scheme or parts.netloc:
        return "/"
    if parts.path.startswith(CALLBACK_PATH) or parts.path.startswith("/api/auth/google/start"):
        return "/"
    return value


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _fail(request: Request, code: str) -> RedirectResponse:
    resp = RedirectResponse(f"/?login_error={code}", status_code=302)
    _clear_oauth_cookie(resp, request)
    return resp


def _clear_oauth_cookie(resp, request: Request) -> None:
    resp.delete_cookie(OAUTH_COOKIE, path=OAUTH_COOKIE_PATH, httponly=True,
                       samesite="lax", secure=auth.is_https(request))


@router.get("/start")
async def start(request: Request, next: Optional[str] = None):
    target = safe_next(next)
    creds = auth.google_credentials()
    base = auth.public_url()
    data = auth.load_auth()
    if creds is None or not base or data is None:
        return _fail(request, "misconfigured")
    # the am_oauth cookie must be set on the host Google returns to
    if auth.host_name(request) != auth.public_host():
        return RedirectResponse(f"{base}/api/auth/google/start?next={quote(target, safe='')}",
                                status_code=302)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)          # 64 chars (RFC 7636: 43-128)
    challenge = _b64e(hashlib.sha256(verifier.encode("ascii")).digest())
    cookie = auth.sign_value("oauth", {"state": state, "nonce": nonce, "verifier": verifier,
                                       "next": target, "iat": int(time.time())}, data)
    params = {
        "client_id": creds["clientId"],
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": redirect_uri(),
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    resp = RedirectResponse(f"{AUTH_ENDPOINT}?{urlencode(params)}", status_code=302)
    resp.set_cookie(OAUTH_COOKIE, cookie, max_age=OAUTH_MAX_AGE, path=OAUTH_COOKIE_PATH,
                    httponly=True, samesite="lax", secure=auth.is_https(request))
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _jwt_claims(token: str) -> Optional[dict]:
    try:
        _header, payload, _sig = token.split(".")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, TypeError):
        return None
    return claims if isinstance(claims, dict) else None


def check_id_token(claims: dict, client_id: str, nonce: str,
                   now: Optional[float] = None) -> Optional[str]:
    """The (lowercased) verified email, or None when a claim is wrong."""
    now = now if now is not None else time.time()
    if claims.get("iss") not in ISSUERS:
        return None
    aud = claims.get("aud")
    auds = aud if isinstance(aud, list) else [aud]
    if client_id not in auds:
        return None
    if len(auds) > 1 and claims.get("azp") != client_id:
        return None
    try:
        exp = float(claims["exp"])
        iat = float(claims.get("iat", now))
    except (KeyError, TypeError, ValueError):
        return None
    if exp <= now - CLOCK_SKEW_S or iat > now + CLOCK_SKEW_S:
        return None
    got_nonce = claims.get("nonce")
    if not isinstance(got_nonce, str) or not hmac.compare_digest(got_nonce, nonce):
        return None
    verified = claims.get("email_verified")
    if not (verified is True or verified == "true"):
        return None
    email = claims.get("email")
    if not isinstance(email, str) or not email:
        return None
    return email.strip().lower()


@router.get("/callback")
async def callback(request: Request, code: Optional[str] = None,
                   state: Optional[str] = None, error: Optional[str] = None):
    ip = auth.client_ip(request)
    if auth.limiter.reserve(ip):
        return _fail(request, "rate")
    data = auth.load_auth()
    creds = auth.google_credentials()
    if data is None or creds is None or not auth.public_url():
        return _fail(request, "misconfigured")
    oauth = auth.read_value("oauth", request.cookies.get(OAUTH_COOKIE), OAUTH_MAX_AGE, data)
    if oauth is None or not isinstance(oauth.get("state"), str) or not state \
            or not hmac.compare_digest(oauth["state"], state):
        await asyncio.sleep(auth.FAILURE_DELAY_S)
        return _fail(request, "invalid")
    if error:
        # the user cancelled on Google's page (access_denied) or similar
        return _fail(request, "denied")
    if not code:
        return _fail(request, "invalid")

    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(),
        "client_id": creds["clientId"],
        "client_secret": creds["clientSecret"],
        "code_verifier": str(oauth.get("verifier", "")),
    }
    try:
        async with _client() as client:
            r = await client.post(TOKEN_ENDPOINT, data=form,
                                  headers={"Accept": "application/json"})
        body = r.json() if r.content else {}
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Google token request failed: %s", type(e).__name__)
        return _fail(request, "invalid")
    if r.status_code != 200 or not isinstance(body, dict):
        err = body.get("error") if isinstance(body, dict) else None
        logger.warning("Google token endpoint returned %s (%s)", r.status_code,
                       err if isinstance(err, str) else "?")
        if err in ("invalid_client", "unauthorized_client") or r.status_code == 401:
            return _fail(request, "misconfigured")
        return _fail(request, "invalid")
    id_token = body.get("id_token")
    claims = _jwt_claims(id_token) if isinstance(id_token, str) else None
    email = check_id_token(claims, creds["clientId"], str(oauth.get("nonce", ""))) \
        if claims else None
    if email is None:
        logger.warning("Google ID token rejected (claims check)")
        return _fail(request, "invalid")
    if email not in auth.allowed_emails():
        logger.warning("Google sign-in refused for an address not in googleAllowedEmails")
        return _fail(request, "not_allowed")

    auth.limiter.reset(ip)
    resp = RedirectResponse(safe_next(oauth.get("next")), status_code=302)
    _clear_oauth_cookie(resp, request)
    auth.set_session_cookie(resp, request, data, email=email)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------- settings (gated)

class AllowedEmails(BaseModel):
    emails: List[str]


def _config_view() -> dict:
    return {
        "configured": auth.google_configured(),
        "publicUrl": auth.public_url(),
        "redirectUri": redirect_uri() if auth.public_url() else "",
        "allowedEmails": sorted(auth.allowed_emails()),
        "passwordLogin": auth.password_login_setting(),
        "password": auth.has_password(),
    }


@router.get("")
async def google_config():
    """What the Settings → Access block shows. No client id or secret."""
    return _config_view()


@router.put("/allowed")
async def set_allowed(req: AllowedEmails):
    if len(req.emails) > MAX_EMAILS:
        raise HTTPException(400, f"at most {MAX_EMAILS} addresses")
    emails: List[str] = []
    for raw in req.emails:
        try:
            e = auth.normalize_email(raw)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        if e not in emails:
            emails.append(e)
    if not emails and not auth.password_login_setting():
        raise HTTPException(409, "password login is off: keep at least one allowed "
                                 "email, or turn password login back on first")
    config.settings.auth.googleAllowedEmails = emails
    config.save_settings(config.settings)
    return _config_view()
