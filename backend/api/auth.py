"""Login endpoints for the single-password gate (see backend/core/auth.py).

``status``, ``login`` and ``logout`` are public; ``password`` and
``logout-all`` pass the gate middleware first, so they need a session or a
local caller."""
import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])

# paths the gate middleware lets through without a session
PUBLIC_PATHS = {
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
}


class LoginRequest(BaseModel):
    password: str


class PasswordChange(BaseModel):
    current: str
    new: str


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


@router.get("/status")
async def status(request: Request):
    return {
        "configured": auth.is_configured(),
        "authenticated": auth.session_claims(request) is not None,
        "local": auth.is_local(request),
    }


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    if not auth.is_configured():
        raise HTTPException(503, "no password set: run "
                                 "`python -m backend.core.auth set-password` on the server")
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
        raise HTTPException(409, "no password set")
    auth.bump_version()
    resp = JSONResponse({"ok": True})
    auth.clear_session_cookie(resp, request)
    return resp


@router.post("/password")
async def change_password(req: PasswordChange, request: Request):
    """Change the password; every other session ends (version bump) and the
    caller gets a fresh cookie. First-time setup is CLI only."""
    if not auth.is_configured():
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
        auth.set_session_cookie(resp, request, data)
    return resp
