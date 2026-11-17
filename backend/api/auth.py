"""Login endpoints for the gate (see backend/core/auth.py; Google sign-in
is backend/api/auth_google.py).

``status``, ``login`` and ``logout`` are public; ``password``,
``password-login`` and ``logout-all`` pass the gate middleware first, so
they need a session or a local caller."""
import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core import auth, config
from . import auth_google

router = APIRouter(prefix="/api/auth", tags=["auth"])

# paths the gate middleware lets through without a session
PUBLIC_PATHS = {
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
} | auth_google.PUBLIC_PATHS


class LoginRequest(BaseModel):
    password: str


class PasswordChange(BaseModel):
    current: str
    new: str


class PasswordLoginToggle(BaseModel):
    enabled: bool


def _too_many(retry: int) -> JSONResponse:
    return JSONResponse({"detail": "too many failed attempts",
                         "retryAfter": retry},
                        status_code=429, headers={"Retry-After": str(retry)})


async def _verify_limited(request: Request, password: str):
    """None when ``password`` is right, else the error response to return.
    Failures are rate limited per client address. The attempt is reserved
    (counted as a failure) before the slow password check and undone on
    success, so a parallel burst can't exceed the limit."""
    ip = auth.client_ip(request)
    retry = auth.limiter.reserve(ip)
    if retry:
        return _too_many(retry)
    ok = await asyncio.to_thread(auth.check_password, password)
    if ok:
        auth.limiter.reset(ip)
        return None
    await asyncio.sleep(auth.FAILURE_DELAY_S)
    return JSONResponse({"detail": "wrong password"}, status_code=401)


def password_login_allowed(request: Request) -> bool:
    """The password form works for this caller: a password is set and
    either password login is on or the caller is local."""
    return auth.has_password() and (auth.password_login_setting()
                                    or auth.is_local(request))


@router.get("/status")
async def status(request: Request):
    """Public. ``google``: the Google button works on this page (a client
    is stored, publicUrl is set and this request's Host is publicUrl's);
    ``googleUrl``: where it does, when it is set up but this is another
    host. Never any secret."""
    claims = auth.session_claims(request)
    google_ready = auth.google_ready()
    google = google_ready and auth.google_available(request)
    return {
        "configured": auth.is_configured(),
        "authenticated": claims is not None,
        "local": auth.is_local(request),
        "passwordLogin": password_login_allowed(request),
        "google": google,
        "googleUrl": auth.public_url() if google_ready and not google else None,
        "email": (claims or {}).get("email"),
    }


@router.put("/password-login")
async def set_password_login(req: PasswordLoginToggle):
    """Turn the password form on/off for remote browsers. Off needs a
    working Google sign-in first (client, publicUrl, an allowed address)."""
    if not req.enabled and not (auth.google_ready() and auth.allowed_emails()):
        raise HTTPException(409, "set up Google sign-in first (a Google client, "
                                 "auth.publicUrl and at least one allowed email): "
                                 "turning password login off would lock you out")
    config.settings.auth.passwordLogin = req.enabled
    config.save_settings(config.settings)
    return {"ok": True, "passwordLogin": req.enabled}


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    if not auth.has_password():
        raise HTTPException(503, "no password set: run "
                                 "`python -m backend.core.auth set-password` on the server")
    if not password_login_allowed(request):
        raise HTTPException(403, "password login is disabled")
    err = await _verify_limited(request, req.password)
    if err is not None:
        return err
    resp = JSONResponse({"ok": True})
    auth.set_session_cookie(resp, request)
    return resp


@router.post("/logout")
async def logout(request: Request):
    resp = JSONResponse({"ok": True})
    auth.clear_session_cookie(resp, request)
    return resp


@router.post("/logout-all")
async def logout_all(request: Request):
    """Sign out every device (bumps the session version). The caller's own
    cookie is cleared too."""
    if not auth.is_configured():
        raise HTTPException(409, "login is not configured")
    auth.bump_version()
    resp = JSONResponse({"ok": True})
    auth.clear_session_cookie(resp, request)
    return resp


@router.post("/password")
async def change_password(req: PasswordChange, request: Request):
    """Change the password; every other session ends (version bump) and the
    caller gets a fresh cookie. First-time setup is CLI only."""
    if not auth.has_password():
        raise HTTPException(409, "no password set: run "
                                 "`python -m backend.core.auth set-password` on the server")
    if len(req.new) < auth.MIN_PASSWORD_LEN:
        raise HTTPException(400, f"the new password must be at least "
                                 f"{auth.MIN_PASSWORD_LEN} characters")
    err = await _verify_limited(request, req.current)
    if err is not None:
        if err.status_code == 401:
            return JSONResponse({"detail": "current password is wrong"},
                                status_code=403)
        return err
    data = await asyncio.to_thread(auth.set_password, req.new)
    resp = JSONResponse({"ok": True})
    if not auth.is_local(request):
        email = (auth.session_claims(request) or {}).get("email")
        auth.set_session_cookie(resp, request, data, email=email)
    return resp
