"""Single-password login gate.

State lives in ``data/auth.json`` (atomic write, chmod 600)::

    {"hash": "scrypt$16384$8$1$<salt>$<key>", "secret": "<64 hex>", "version": 1}

A session is the cookie ``am_session`` = ``b64url({"v","iat"}).b64url(hmac)``,
signed with ``secret``. Bumping ``version`` (``logout-all``, password change)
invalidates every issued cookie at once.

Local callers — peer 127.0.0.1/::1 with no forwarding headers — never need a
session: the MCP tools, agent_cli and the Comics converter call
http://127.0.0.1:5180 directly. A request relayed by the reverse proxy
(``settings.auth.trustedProxy``) is never local.

CLI (run on the server)::

    .venv/bin/python -m backend.core.auth set-password          # prompts twice
    printf '%s\\n' "$PW" | .venv/bin/python -m backend.core.auth set-password --stdin
    .venv/bin/python -m backend.core.auth logout-all
    .venv/bin/python -m backend.core.auth status
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

from . import config
from .config import DATA_DIR, atomic_write_json

AUTH_FILE: Path = DATA_DIR / "auth.json"

COOKIE_NAME = "am_session"
SESSION_MAX_AGE = 400 * 24 * 3600      # browsers cap cookie lifetime at 400 days
SESSION_REFRESH_AFTER = 30 * 24 * 3600  # rolling re-issue once a cookie is this old
MIN_PASSWORD_LEN = 8

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1
_SCRYPT_DKLEN = 32

LOOPBACK = {"127.0.0.1", "::1"}
FORWARD_HEADERS = ("x-forwarded-for", "forwarded", "x-real-ip")


# ---------------------------------------------------------------- hashing

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N,
                         r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64e(salt)}${_b64e(key)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, key = stored.split("$")
        if algo != "scrypt":
            return False
        expected = _b64d(key)
        got = hashlib.scrypt(password.encode("utf-8"), salt=_b64d(salt),
                             n=int(n), r=int(r), p=int(p), dklen=len(expected),
                             maxmem=64 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


# ---------------------------------------------------------------- storage

_cache: dict = {"key": None, "data": None}
_cache_lock = threading.Lock()


def load_auth() -> Optional[dict]:
    """The auth record, or None when no password is set. Cached on the file's
    mtime/size so a CLI change is picked up by the running server."""
    try:
        st = AUTH_FILE.stat()
    except OSError:
        return None
    key = (str(AUTH_FILE), st.st_mtime_ns, st.st_size)
    with _cache_lock:
        if _cache["key"] == key:
            return _cache["data"]
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not (isinstance(data, dict) and data.get("hash") and data.get("secret")):
            data = None
    except (OSError, ValueError):
        data = None
    with _cache_lock:
        _cache["key"], _cache["data"] = key, data
    return data


def _save_auth(data: dict) -> None:
    atomic_write_json(AUTH_FILE, data, indent=2)
    try:
        os.chmod(AUTH_FILE, 0o600)
    except OSError:
        pass


def is_configured() -> bool:
    return load_auth() is not None


def set_password(password: str) -> dict:
    """Store a new password hash and bump ``version`` (all sessions end)."""
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
    current = load_auth() or {}
    data = {
        "hash": hash_password(password),
        "secret": current.get("secret") or secrets.token_hex(32),
        "version": int(current.get("version", 0)) + 1,
    }
    _save_auth(data)
    return data


def bump_version() -> dict:
    current = load_auth()
    if current is None:
        raise RuntimeError("no password is set")
    data = dict(current, version=int(current.get("version", 0)) + 1)
    _save_auth(data)
    return data


def check_password(password: str) -> bool:
    data = load_auth()
    return bool(data) and verify_password(password, data["hash"])


# ---------------------------------------------------------------- session tokens

def _sign(secret: str, payload: str) -> str:
    return _b64e(hmac.new(secret.encode("utf-8"), payload.encode("ascii"),
                          hashlib.sha256).digest())


def make_token(data: Optional[dict] = None, now: Optional[float] = None) -> str:
    data = data or load_auth()
    if data is None:
        raise RuntimeError("no password is set")
    iat = int(now if now is not None else time.time())
    payload = _b64e(json.dumps({"v": int(data["version"]), "iat": iat},
                               separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_sign(data['secret'], payload)}"


def read_token(token: Optional[str], data: Optional[dict] = None,
               now: Optional[float] = None) -> Optional[dict]:
    """The token's claims when it is genuine, current-version and unexpired."""
    if not token:
        return None
    data = data or load_auth()
    if data is None:
        return None
    try:
        payload, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, _sign(data["secret"], payload)):
            return None
        claims = json.loads(_b64d(payload))
        v, iat = int(claims["v"]), int(claims["iat"])
    except (ValueError, KeyError, TypeError):
        return None
    now = now if now is not None else time.time()
    if v != int(data["version"]) or iat > now + 300 or now - iat >= SESSION_MAX_AGE:
        return None
    return {"v": v, "iat": iat}


def needs_refresh(claims: dict, now: Optional[float] = None) -> bool:
    now = now if now is not None else time.time()
    return now - claims["iat"] >= SESSION_REFRESH_AFTER


# ---------------------------------------------------------------- request helpers

def trusted_proxy() -> str:
    try:
        return config.settings.auth.trustedProxy.strip()
    except AttributeError:
        return ""


def peer_ip(request) -> str:
    return request.client.host if request.client else ""


def _from_proxy(request) -> bool:
    proxy = trusted_proxy()
    return bool(proxy) and peer_ip(request) == proxy


def is_local(request) -> bool:
    """Loopback peer and nothing relayed: a process on this machine."""
    if peer_ip(request) not in LOOPBACK:
        return False
    return not any(h in request.headers for h in FORWARD_HEADERS)


def client_ip(request) -> str:
    """The rate-limit key: the proxy's last X-Forwarded-For entry (the address
    Caddy saw; earlier entries are client-supplied) when the peer is the
    trusted proxy, else the peer itself."""
    if _from_proxy(request):
        xff = request.headers.get("x-forwarded-for", "")
        last = xff.split(",")[-1].strip() if xff else ""
        if last:
            return last
    return peer_ip(request)


def is_https(request) -> bool:
    """Only the trusted proxy may tell us the browser used https."""
    if not _from_proxy(request):
        return False
    proto = request.headers.get("x-forwarded-proto", "")
    return proto.split(",")[-1].strip().lower() == "https"


def session_claims(request) -> Optional[dict]:
    return read_token(request.cookies.get(COOKIE_NAME))


def set_session_cookie(response, request, data: Optional[dict] = None) -> None:
    response.set_cookie(
        COOKIE_NAME, make_token(data), max_age=SESSION_MAX_AGE, path="/",
        httponly=True, samesite="lax", secure=is_https(request))


def clear_session_cookie(response, request) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True,
                           samesite="lax", secure=is_https(request))


# ---------------------------------------------------------------- rate limit

class LoginLimiter:
    """Failed logins: ``per_ip`` per ``window`` per address, and ``global_max``
    per ``global_window`` across all addresses."""

    def __init__(self, per_ip: int = 5, window: float = 15 * 60,
                 global_max: int = 30, global_window: float = 3600):
        self.per_ip, self.window = per_ip, window
        self.global_max, self.global_window = global_max, global_window
        self._ip: dict[str, deque] = {}
        self._global: deque = deque()
        self._lock = threading.Lock()

    @staticmethod
    def _prune(q: deque, horizon: float) -> None:
        while q and q[0] <= horizon:
            q.popleft()

    def retry_after(self, ip: str, now: Optional[float] = None) -> int:
        """Seconds until ``ip`` may try again; 0 when allowed now."""
        now = now if now is not None else time.time()
        with self._lock:
            wait = 0.0
            q = self._ip.get(ip)
            if q is not None:
                self._prune(q, now - self.window)
                if len(q) >= self.per_ip:
                    wait = max(wait, q[0] + self.window - now)
                if not q:
                    self._ip.pop(ip, None)
            self._prune(self._global, now - self.global_window)
            if len(self._global) >= self.global_max:
                wait = max(wait, self._global[0] + self.global_window - now)
        return int(wait) + 1 if wait > 0 else 0

    def record_failure(self, ip: str, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        with self._lock:
            self._ip.setdefault(ip, deque()).append(now)
            self._global.append(now)

    def reset(self, ip: str) -> None:
        with self._lock:
            self._ip.pop(ip, None)

    def clear(self) -> None:
        with self._lock:
            self._ip.clear()
            self._global.clear()


limiter = LoginLimiter()
FAILURE_DELAY_S = 0.5


# ---------------------------------------------------------------- CLI

def _read_new_password(from_stdin: bool) -> str:
    import sys
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    import getpass
    first = getpass.getpass("New AutoManga password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        raise SystemExit("passwords do not match")
    return first


def main(argv: Optional[list] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="python -m backend.core.auth",
                                     description="AutoManga login gate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("set-password", help="set or change the password "
                        "(also signs out every session)")
    sp.add_argument("--stdin", action="store_true",
                    help="read the password from the first line of stdin")
    sub.add_parser("logout-all", help="invalidate every session cookie")
    sub.add_parser("status", help="show whether a password is set")
    args = parser.parse_args(argv)

    if args.cmd == "set-password":
        try:
            data = set_password(_read_new_password(args.stdin))
        except ValueError as e:
            raise SystemExit(str(e))
        print(f"password set in {AUTH_FILE} (session version {data['version']})")
    elif args.cmd == "logout-all":
        try:
            data = bump_version()
        except RuntimeError as e:
            raise SystemExit(str(e))
        print(f"all sessions signed out (session version {data['version']})")
    else:
        data = load_auth()
        print(f"{AUTH_FILE}: " + (f"configured, session version {data['version']}"
                                  if data else "no password set"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
