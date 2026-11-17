"""Login gate (backend/core/auth.py, backend/api/auth.py, main.auth_gate).

Every test points AUTH_FILE at a temp dir: the real data/auth.json is never
touched."""
import time

import pytest
from fastapi.testclient import TestClient

from backend.core import auth, config
from backend.main import app

PROXY = "192.168.1.11"
PW = "correct horse battery"


@pytest.fixture(autouse=True)
def isolated_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr(auth, "FAILURE_DELAY_S", 0)
    monkeypatch.setattr(config.settings.auth, "trustedProxy", PROXY)
    auth.limiter.clear()
    yield tmp_path / "auth.json"
    auth.limiter.clear()


@pytest.fixture
def configured(isolated_auth):
    auth.set_password(PW)
    return isolated_auth


def remote():
    return TestClient(app, client=("203.0.113.7", 40000))


def local():
    return TestClient(app, client=("127.0.0.1", 50000))


def via_proxy(ip="198.51.100.9", proto="https"):
    c = TestClient(app, client=(PROXY, 41000))
    c.headers.update({"X-Forwarded-For": f"10.6.6.6, {ip}",
                      "X-Forwarded-Proto": proto})
    return c


# ---------------------------------------------------------------- core

def test_hash_round_trip():
    h = auth.hash_password(PW)
    assert h.startswith("scrypt$16384$8$1$")
    assert auth.verify_password(PW, h)
    assert not auth.verify_password(PW + "x", h)
    assert not auth.verify_password(PW, "garbage")


def test_auth_file_is_private(configured):
    data = auth.load_auth()
    assert len(bytes.fromhex(data["secret"])) == 32
    assert data["version"] == 1
    assert configured.stat().st_mode & 0o777 == 0o600


def test_tampered_cookie_rejected(configured):
    tok = auth.make_token()
    assert auth.read_token(tok) is not None
    payload, sig = tok.split(".")
    forged = auth._b64e(b'{"v":1,"iat":%d}' % (int(time.time()) + 1))
    assert auth.read_token(f"{forged}.{sig}") is None
    assert auth.read_token(f"{payload}.{sig[:-2]}AA") is None
    assert auth.read_token("nonsense") is None


def test_expired_cookie_rejected(configured):
    now = time.time()
    tok = auth.make_token(now=now - auth.SESSION_MAX_AGE - 5)
    assert auth.read_token(tok, now=now) is None


def test_version_bump_invalidates(configured):
    tok = auth.make_token()
    auth.bump_version()
    assert auth.read_token(tok) is None
    assert auth.read_token(auth.make_token()) is not None


def test_cli_set_password_stdin_and_logout_all(isolated_auth, monkeypatch, capsys):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(PW + "\n"))
    assert auth.main(["set-password", "--stdin"]) == 0
    assert auth.check_password(PW)
    v = auth.load_auth()["version"]
    assert auth.main(["logout-all"]) == 0
    assert auth.load_auth()["version"] == v + 1
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    with pytest.raises(SystemExit):
        auth.main(["set-password", "--stdin"])


# ---------------------------------------------------------------- gate

def test_remote_401_then_200_after_login(configured):
    c = remote()
    r = c.get("/api/settings/")
    assert r.status_code == 401
    assert r.json()["detail"] == "authentication required"
    st = c.get("/api/auth/status").json()
    assert st == {"configured": True, "authenticated": False, "local": False}
    assert c.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    r = c.post("/api/auth/login", json={"password": PW})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "am_session=" in cookie and "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower() and "Path=/" in cookie
    assert "Secure" not in cookie
    assert c.get("/api/settings/").status_code == 200
    assert c.get("/api/auth/status").json()["authenticated"] is True
    c.post("/api/auth/logout")
    assert c.get("/api/settings/").status_code == 401


def test_public_paths_pass(configured):
    c = remote()
    assert c.get("/api/health").status_code == 200
    assert c.get("/").status_code == 200          # SPA shell
    assert c.get("/api/auth/status").status_code == 200


def test_local_passes_without_cookie(configured):
    c = local()
    assert c.get("/api/settings/").status_code == 200
    assert c.get("/api/auth/status").json()["local"] is True


@pytest.mark.parametrize("hdr", [
    {"X-Forwarded-For": "1.2.3.4"},
    {"Forwarded": "for=1.2.3.4"},
    {"X-Real-IP": "1.2.3.4"},
])
def test_loopback_with_forwarding_header_is_not_local(configured, hdr):
    r = local().get("/api/settings/", headers=hdr)
    assert r.status_code == 401


def test_proxy_is_never_local(configured):
    c = TestClient(app, client=(PROXY, 41000))
    assert c.get("/api/settings/").status_code == 401


def test_sixth_failure_is_429(configured):
    c = remote()
    for _ in range(5):
        assert c.post("/api/auth/login", json={"password": "x"}).status_code == 401
    r = c.post("/api/auth/login", json={"password": PW})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    # a different address is not affected
    other = TestClient(app, client=("203.0.113.8", 40000))
    assert other.post("/api/auth/login", json={"password": PW}).status_code == 200


def test_rate_limit_keys_on_proxy_xff(configured):
    for _ in range(5):
        via_proxy("198.51.100.1").post("/api/auth/login", json={"password": "x"})
    assert via_proxy("198.51.100.1").post(
        "/api/auth/login", json={"password": PW}).status_code == 429
    assert via_proxy("198.51.100.2").post(
        "/api/auth/login", json={"password": PW}).status_code == 200


def test_global_cap():
    lim = auth.LoginLimiter(global_max=3)
    for i in range(3):
        lim.record_failure(f"10.0.0.{i}", now=1000)
    assert lim.retry_after("10.9.9.9", now=1001) > 0
    assert lim.retry_after("10.9.9.9", now=1000 + 3601) == 0


def test_client_ip_ignores_xff_from_untrusted_peer():
    from starlette.requests import Request

    def req(peer, xff):
        return Request({"type": "http", "client": (peer, 1), "headers": [
            (b"x-forwarded-for", xff.encode())]})
    assert auth.client_ip(req("203.0.113.7", "1.1.1.1")) == "203.0.113.7"
    assert auth.client_ip(req(PROXY, "1.1.1.1, 2.2.2.2")) == "2.2.2.2"


def test_cross_origin_post_403(configured):
    c = remote()
    c.post("/api/auth/login", json={"password": PW})
    r = c.post("/api/agent/projects", json={"name": "x"},
               headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    # a local caller (browser on this Mac) is protected too
    r = local().post("/api/agent/projects", json={"name": "x"},
                     headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    # login CSRF is refused as well
    assert remote().post("/api/auth/login", json={"password": PW},
                         headers={"Origin": "https://evil.example"}).status_code == 403


def test_same_origin_post_allowed(configured):
    c = local()
    r = c.post("/api/auth/logout", headers={"Origin": "http://testserver"})
    assert r.status_code == 200
    # the vite dev server (localhost:5173 → :5180) from this machine
    r = c.post("/api/auth/logout", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200


def test_not_configured_503_remote_but_local_ok(isolated_auth):
    assert remote().get("/api/settings/").status_code == 503
    assert remote().post("/api/auth/login", json={"password": PW}).status_code == 503
    assert remote().get("/api/auth/status").json()["configured"] is False
    assert local().get("/api/settings/").status_code == 200


def test_secure_flag_only_via_proxy(configured):
    r = via_proxy().post("/api/auth/login", json={"password": PW})
    assert r.status_code == 200 and "Secure" in r.headers["set-cookie"]
    r = via_proxy(proto="http").post("/api/auth/login", json={"password": PW})
    assert "Secure" not in r.headers["set-cookie"]
    # a direct client claiming https is ignored
    r = remote().post("/api/auth/login", json={"password": PW},
                      headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200 and "Secure" not in r.headers["set-cookie"]


def test_rolling_refresh(configured):
    c = remote()
    old = auth.make_token(now=time.time() - auth.SESSION_REFRESH_AFTER - 10)
    c.cookies.set(auth.COOKIE_NAME, old)
    r = c.get("/api/settings/")
    assert r.status_code == 200 and "am_session=" in r.headers.get("set-cookie", "")
    fresh = remote()
    fresh.cookies.set(auth.COOKIE_NAME, auth.make_token())
    r = fresh.get("/api/settings/")
    assert r.status_code == 200 and "set-cookie" not in r.headers


def test_change_password_bumps_version(configured):
    a, b = remote(), TestClient(app, client=("203.0.113.9", 40000))
    a.post("/api/auth/login", json={"password": PW})
    b.post("/api/auth/login", json={"password": PW})
    r = a.post("/api/auth/password", json={"current": "wrong", "new": "another pass"})
    assert r.status_code == 403
    r = a.post("/api/auth/password", json={"current": PW, "new": "short"})
    assert r.status_code == 400
    r = a.post("/api/auth/password", json={"current": PW, "new": "another pass"})
    assert r.status_code == 200
    assert a.get("/api/settings/").status_code == 200   # re-issued cookie
    assert b.get("/api/settings/").status_code == 401   # other device signed out
    assert auth.check_password("another pass")


def test_password_change_requires_session_or_local(configured):
    r = remote().post("/api/auth/password", json={"current": PW, "new": "another pass"})
    assert r.status_code == 401
    r = local().post("/api/auth/password", json={"current": PW, "new": "another pass"})
    assert r.status_code == 200


def test_logout_all(configured):
    a = remote()
    a.post("/api/auth/login", json={"password": PW})
    assert local().post("/api/auth/logout-all").status_code == 200
    assert a.get("/api/settings/").status_code == 401
