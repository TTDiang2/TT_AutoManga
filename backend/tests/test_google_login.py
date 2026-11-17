"""Sign in with Google (backend/api/auth_google.py) and the password-login
switch. auth.json and settings.json live in a temp dir; Google's token
endpoint is an httpx.MockTransport. Nothing touches the real data/."""
import base64
import io
import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api import auth_google
from backend.core import auth, config
from backend.main import app

PROXY = "192.168.1.11"
PUBLIC = "https://manga.example.dk"
HOST = "manga.example.dk"
LAN = "192.168.1.177"
CID = "1234567890-abcdefg.apps.googleusercontent.com"
CSECRET = "GOCSPX-super-secret-value-123"
OWNER = "owner@example.com"
PW = "correct horse battery"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(auth, "FAILURE_DELAY_S", 0)
    monkeypatch.setattr(auth, "_local_names", frozenset({LAN}))
    monkeypatch.setattr(config.settings, "auth", config.AuthConfig(
        trustedProxy=PROXY, publicUrl=PUBLIC, allowedHosts=[HOST],
        googleAllowedEmails=[OWNER]))
    auth.limiter.clear()
    yield tmp_path
    auth.limiter.clear()


@pytest.fixture
def google():
    auth.set_password(PW)
    auth.set_google(CID, CSECRET)


class FakeGoogle:
    """Google's token endpoint. ``claims`` overrides go into the ID token."""

    def __init__(self, monkeypatch):
        self.requests = []
        self.status = 200
        self.body = None
        self.overrides = {}
        self.nonce = None
        self.raise_error = False
        monkeypatch.setattr(auth_google, "_client", lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(self.handle)))

    def id_token(self):
        now = int(time.time())
        claims = {"iss": "https://accounts.google.com", "aud": CID, "azp": CID,
                  "sub": "1087", "email": OWNER, "email_verified": True,
                  "iat": now, "exp": now + 3600, "nonce": self.nonce}
        claims.update(self.overrides)
        claims = {k: v for k, v in claims.items() if v is not ...}

        def enc(obj):
            return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
        return f"{enc({'alg': 'RS256', 'kid': 'k'})}.{enc(claims)}.c2ln"

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_error:
            raise httpx.ConnectError("boom", request=request)
        if self.body is not None:
            return httpx.Response(self.status, json=self.body)
        return httpx.Response(self.status, json={
            "access_token": "ya29.access-token-xyz", "token_type": "Bearer",
            "expires_in": 3599, "scope": "openid email profile",
            "id_token": self.id_token()})


@pytest.fixture
def fake(monkeypatch):
    return FakeGoogle(monkeypatch)


def public(ip="198.51.100.9"):
    """A browser on the internet, through Caddy, at the public name."""
    c = TestClient(app, base_url=PUBLIC, client=(PROXY, 41000))
    c.headers.update({"X-Forwarded-For": ip, "X-Forwarded-Proto": "https"})
    return c


def lan():
    return TestClient(app, base_url=f"http://{LAN}:5180", client=("192.168.1.50", 40000))


def local():
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


def begin(c, next_path="/library?x=1"):
    r = c.get("/api/auth/google/start", params={"next": next_path}, follow_redirects=False)
    assert r.status_code == 302, r.text
    loc = urlsplit(r.headers["location"])
    q = {k: v[0] for k, v in parse_qs(loc.query).items()}
    return r, loc, q


def finish(c, fake, q, **params):
    fake.nonce = q["nonce"]
    p = {"code": "4/auth-code", "state": q["state"]}
    p.update(params)
    return c.get("/api/auth/google/callback", params=p, follow_redirects=False)


def login_error(r):
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("/?login_error="), loc
    return loc.split("=", 1)[1]


# ---------------------------------------------------------------- start

def test_start_redirect_params(google):
    c = public()
    r, loc, q = begin(c)
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == auth_google.AUTH_ENDPOINT
    assert q["response_type"] == "code"
    assert q["scope"] == "openid email profile"
    assert q["client_id"] == CID
    assert q["redirect_uri"] == PUBLIC + "/api/auth/google/callback"
    assert q["prompt"] == "select_account"
    assert q["code_challenge_method"] == "S256"
    assert len(q["state"]) >= 32 and len(q["nonce"]) >= 32
    assert CSECRET not in r.headers["location"]
    cookie = r.headers["set-cookie"]
    assert "am_oauth=" in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert "samesite=lax" in cookie.lower() and "Path=/api/auth/google" in cookie
    assert "Max-Age=600" in cookie
    # PKCE: the challenge is S256 of the verifier kept in the signed cookie
    import hashlib
    st = auth.read_value("oauth", c.cookies.get("am_oauth"), 600)
    assert st["state"] == q["state"] and st["nonce"] == q["nonce"]
    assert st["next"] == "/library?x=1"
    want = base64.urlsafe_b64encode(
        hashlib.sha256(st["verifier"].encode()).digest()).rstrip(b"=").decode()
    assert q["code_challenge"] == want
    assert CSECRET not in json.dumps(st)


def test_redirect_uri_comes_from_config_not_host(google):
    # a direct request on the public name with another port and plain http:
    # the redirect_uri is still exactly publicUrl + callback
    c = TestClient(app, base_url=f"http://{HOST}:5180", client=(PROXY, 41000))
    _, _, q = begin(c)
    assert q["redirect_uri"] == PUBLIC + "/api/auth/google/callback"
    # an unrelated Host never becomes the redirect_uri: LAN → sent to the public start
    r = lan().get("/api/auth/google/start", params={"next": "/x"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == PUBLIC + "/api/auth/google/start?next=%2Fx"
    assert "am_oauth" not in r.headers.get("set-cookie", "")


def test_start_misconfigured(isolated):
    auth.set_password(PW)
    r = public().get("/api/auth/google/start", follow_redirects=False)
    assert login_error(r) == "misconfigured"
    auth.set_google(CID, CSECRET)
    config.settings.auth.publicUrl = ""
    r = public().get("/api/auth/google/start", follow_redirects=False)
    assert login_error(r) == "misconfigured"


def test_start_and_callback_pass_the_gate_unauthenticated(google, fake):
    c = public()
    assert c.get("/api/settings/").status_code == 401
    _, _, q = begin(c)
    r = finish(c, fake, q)
    assert r.status_code == 302 and r.headers["location"] == "/library?x=1"


# ---------------------------------------------------------------- callback

def test_callback_happy_path(google, fake):
    c = public()
    _, _, q = begin(c, "/comics")
    r = finish(c, fake, q)
    assert r.status_code == 302
    assert r.headers["location"] == "/comics"
    cookies = r.headers.get_list("set-cookie")
    sess = next(h for h in cookies if h.startswith("am_session="))
    assert "HttpOnly" in sess and "Secure" in sess
    assert any(h.startswith("am_oauth=") and "Max-Age=0" in h for h in cookies)
    claims = auth.read_token(c.cookies.get("am_session"))
    assert claims["email"] == OWNER
    assert c.get("/api/settings/").status_code == 200
    st = c.get("/api/auth/status").json()
    assert st["authenticated"] is True and st["email"] == OWNER
    # the token request: client_secret_post + PKCE verifier + config redirect_uri
    (req,) = fake.requests
    assert str(req.url) == auth_google.TOKEN_ENDPOINT
    form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
    assert form["grant_type"] == "authorization_code"
    assert form["code"] == "4/auth-code"
    assert form["client_id"] == CID and form["client_secret"] == CSECRET
    assert form["redirect_uri"] == PUBLIC + "/api/auth/google/callback"
    assert len(form["code_verifier"]) >= 43
    # no token in the redirect or body
    assert "ya29" not in r.text and "ya29" not in r.headers["location"]


def test_old_cookie_without_email_still_valid(google):
    c = public()
    c.cookies.set(auth.COOKIE_NAME, auth.make_token())
    assert c.get("/api/settings/").status_code == 200
    assert c.get("/api/auth/status").json()["email"] is None


def test_wrong_state(google, fake):
    c = public()
    _, _, q = begin(c)
    r = finish(c, fake, q, state="not-the-state")
    assert login_error(r) == "invalid"
    assert fake.requests == []
    assert "am_session" not in c.cookies


def test_missing_or_forged_oauth_cookie(google, fake):
    c = public()
    _, _, q = begin(c)
    c.cookies.clear()
    assert login_error(finish(c, fake, q)) == "invalid"
    # a session token is not an am_oauth value (different key)
    c2 = public()
    _, _, q2 = begin(c2)
    c2.cookies.clear()
    c2.cookies.set("am_oauth", auth.make_token())
    assert login_error(finish(c2, fake, q2)) == "invalid"
    assert fake.requests == []


def test_expired_oauth_cookie(google, fake, monkeypatch):
    c = public()
    _, _, q = begin(c)
    real = time.time
    monkeypatch.setattr(auth.time, "time", lambda: real() + 601)
    assert login_error(finish(c, fake, q)) == "invalid"


@pytest.mark.parametrize("override,code", [
    ({"aud": "someone-else.apps.googleusercontent.com"}, "invalid"),
    ({"aud": [CID, "other"], "azp": "other"}, "invalid"),
    ({"iss": "https://evil.example"}, "invalid"),
    ({"exp": int(time.time()) - 3600}, "invalid"),
    ({"email_verified": False}, "invalid"),
    ({"email_verified": ...}, "invalid"),
    ({"nonce": "replayed-nonce"}, "invalid"),
    ({"email": "stranger@example.com"}, "not_allowed"),
])
def test_bad_id_token(google, fake, override, code):
    fake.overrides = override
    c = public()
    _, _, q = begin(c)
    assert login_error(finish(c, fake, q)) == code
    assert "am_session" not in c.cookies


def test_issuer_without_scheme_and_case_insensitive_email(google, fake):
    fake.overrides = {"iss": "accounts.google.com", "email": "Owner@Example.COM",
                      "email_verified": "true"}
    c = public()
    _, _, q = begin(c)
    r = finish(c, fake, q)
    assert r.headers["location"] == "/library?x=1"
    assert auth.read_token(c.cookies.get("am_session"))["email"] == OWNER


@pytest.mark.parametrize("evil", [
    "//evil.example", "https://evil.example", "/\\evil.example", "\\\\evil",
    "evil", "/\tx", "/\r\nSet-Cookie:x", "javascript:alert(1)",
    "/api/auth/google/start",
])
def test_open_redirect_attempts(google, fake, evil):
    c = public()
    _, _, q = begin(c, evil)
    assert auth.read_value("oauth", c.cookies.get("am_oauth"), 600)["next"] == "/"
    r = finish(c, fake, q)
    assert r.status_code == 302 and r.headers["location"] == "/"


def test_safe_next_unit():
    assert auth_google.safe_next("/a/b?c=d#e") == "/a/b?c=d#e"
    for bad in ("//x", "https://x", "/\\x", "", None, "x", "/a b", "/\x00"):
        assert auth_google.safe_next(bad) == "/"


@pytest.mark.parametrize("status,body,code", [
    (400, {"error": "invalid_grant"}, "invalid"),
    (401, {"error": "invalid_client"}, "misconfigured"),
    (500, {"error": "server_error"}, "invalid"),
    (200, {"access_token": "ya29.x"}, "invalid"),            # no id_token
    (200, {"id_token": "not-a-jwt"}, "invalid"),
])
def test_token_endpoint_errors(google, fake, status, body, code):
    fake.status, fake.body = status, body
    c = public()
    _, _, q = begin(c)
    r = finish(c, fake, q)
    assert login_error(r) == code
    assert "ya29" not in r.headers["location"]


def test_token_endpoint_unreachable(google, fake):
    fake.raise_error = True
    c = public()
    _, _, q = begin(c)
    assert login_error(finish(c, fake, q)) == "invalid"


def test_user_cancelled(google, fake):
    c = public()
    _, _, q = begin(c)
    r = c.get("/api/auth/google/callback",
              params={"error": "access_denied", "state": q["state"]}, follow_redirects=False)
    assert login_error(r) == "denied"
    assert fake.requests == []


def test_callback_failures_are_rate_limited(google, fake):
    for _ in range(5):
        c = public("198.51.100.20")
        _, _, q = begin(c)
        assert login_error(finish(c, fake, q, state="wrong")) == "invalid"
    c = public("198.51.100.20")
    _, _, q = begin(c)
    assert login_error(finish(c, fake, q)) == "rate"
    # another address is unaffected
    c = public("198.51.100.21")
    _, _, q = begin(c)
    assert finish(c, fake, q).headers["location"] == "/library?x=1"


def test_removing_an_email_ends_its_session(google, fake):
    c = public()
    _, _, q = begin(c)
    finish(c, fake, q)
    assert c.get("/api/settings/").status_code == 200
    config.settings.auth.googleAllowedEmails = ["other@example.com"]
    assert c.get("/api/settings/").status_code == 401
    assert c.get("/api/auth/status").json()["authenticated"] is False


# ---------------------------------------------------------------- password login switch

def test_password_login_off_blocks_remote_not_local(google):
    config.settings.auth.passwordLogin = False
    r = public().post("/api/auth/login", json={"password": PW})
    assert r.status_code == 403 and r.json()["detail"] == "password login is disabled"
    r = lan().post("/api/auth/login", json={"password": PW})
    assert r.status_code == 403
    assert local().post("/api/auth/login", json={"password": PW}).status_code == 200
    assert public().get("/api/auth/status").json()["passwordLogin"] is False
    assert local().get("/api/auth/status").json()["passwordLogin"] is True
    config.settings.auth.passwordLogin = True
    assert public().post("/api/auth/login", json={"password": PW}).status_code == 200


def test_password_login_toggle_guard(isolated):
    auth.set_password(PW)
    c = local()
    r = c.put("/api/auth/password-login", json={"enabled": False})
    assert r.status_code == 409 and "Google" in r.json()["detail"]
    auth.set_google(CID, CSECRET)
    config.settings.auth.googleAllowedEmails = []
    assert c.put("/api/auth/password-login", json={"enabled": False}).status_code == 409
    config.settings.auth.googleAllowedEmails = [OWNER]
    config.settings.auth.publicUrl = ""
    assert c.put("/api/auth/password-login", json={"enabled": False}).status_code == 409
    config.settings.auth.publicUrl = PUBLIC
    r = c.put("/api/auth/password-login", json={"enabled": False})
    assert r.status_code == 200 and config.settings.auth.passwordLogin is False
    saved = json.loads(config.SETTINGS_FILE.read_text())
    assert saved["auth"]["passwordLogin"] is False
    # needs a session remotely
    assert public().put("/api/auth/password-login", json={"enabled": True}).status_code == 401
    assert c.put("/api/auth/password-login", json={"enabled": True}).status_code == 200


# ---------------------------------------------------------------- allowed emails endpoint

def test_allowed_emails_endpoint(google):
    c = local()
    r = c.put("/api/auth/google/allowed",
              json={"emails": [" Owner@Example.com ", "b@x.dk", "b@x.dk"]})
    assert r.status_code == 200
    assert r.json()["allowedEmails"] == ["b@x.dk", OWNER]
    assert config.settings.auth.googleAllowedEmails == [OWNER, "b@x.dk"]
    assert json.loads(config.SETTINGS_FILE.read_text())["auth"]["googleAllowedEmails"] \
        == [OWNER, "b@x.dk"]
    for bad in (["not-an-email"], ["a@b"], ["a b@c.dk"], ["<a@b.dk>"], ["x" * 250 + "@a.dk"]):
        r = c.put("/api/auth/google/allowed", json={"emails": bad})
        assert r.status_code == 400, bad
    assert c.put("/api/auth/google/allowed", json={"emails": "a@b.dk"}).status_code == 422
    # empty is fine while password login is on ...
    assert c.put("/api/auth/google/allowed", json={"emails": []}).status_code == 200
    # ... not when it is off
    config.settings.auth.googleAllowedEmails = [OWNER]
    config.settings.auth.passwordLogin = False
    r = c.put("/api/auth/google/allowed", json={"emails": []})
    assert r.status_code == 409
    assert config.settings.auth.googleAllowedEmails == [OWNER]
    # gated
    assert public().put("/api/auth/google/allowed", json={"emails": [OWNER]}).status_code == 401
    assert public().get("/api/auth/google").status_code == 401
    # CSRF
    r = c.put("/api/auth/google/allowed", json={"emails": [OWNER]},
              headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


# ---------------------------------------------------------------- status per Host

def test_status_flags_per_host(google):
    st = public().get("/api/auth/status").json()
    assert st["google"] is True and st["googleUrl"] is None and st["passwordLogin"] is True
    st = lan().get("/api/auth/status").json()
    assert st["google"] is False and st["googleUrl"] == PUBLIC
    config.settings.auth.publicUrl = ""
    st = public().get("/api/auth/status").json()
    assert st["google"] is False and st["googleUrl"] is None


def test_status_without_google(isolated):
    auth.set_password(PW)
    st = public().get("/api/auth/status").json()
    assert st["google"] is False and st["googleUrl"] is None


def test_google_only_setup_is_configured(isolated):
    auth.set_google(CID, CSECRET)
    st = public().get("/api/auth/status").json()
    assert st["configured"] is True and st["passwordLogin"] is False and st["google"] is True
    assert public().post("/api/auth/login", json={"password": PW}).status_code == 503


def test_secrets_never_in_api_responses(google, fake):
    c = public()
    _, _, q = begin(c)
    finish(c, fake, q)
    bodies = [
        c.get("/api/auth/status").text,
        c.get("/api/auth/google").text,
        c.put("/api/auth/google/allowed", json={"emails": [OWNER]}).text,
        c.get("/api/settings/").text,
        local().get("/api/auth/status").text,
        local().get("/api/auth/google").text,
        local().get("/api/settings/").text,
        lan().get("/api/auth/status").text,
    ]
    for b in bodies:
        assert CSECRET not in b and CID not in b
    view = c.get("/api/auth/google").json()
    assert view == {"configured": True, "publicUrl": PUBLIC,
                    "redirectUri": PUBLIC + "/api/auth/google/callback",
                    "allowedEmails": [OWNER], "passwordLogin": True, "password": True}


# ---------------------------------------------------------------- storage + CLI

def test_google_secret_only_in_auth_json(isolated, google):
    data = json.loads(auth.AUTH_FILE.read_text())
    assert data["google"] == {"clientId": CID, "clientSecret": CSECRET}
    assert auth.AUTH_FILE.stat().st_mode & 0o777 == 0o600
    assert auth.check_password(PW)
    # a password change keeps the Google client
    auth.set_password("another pass phrase")
    assert auth.google_credentials()["clientSecret"] == CSECRET
    assert CSECRET not in json.dumps(config.settings.model_dump())


def test_cli_google_commands(isolated, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{CID}\n{CSECRET}\n"))
    assert auth.main(["set-google", "--stdin"]) == 0
    assert auth.google_credentials() == {"clientId": CID, "clientSecret": CSECRET}
    monkeypatch.setattr("sys.stdin", io.StringIO("bad id\n\n"))
    with pytest.raises(SystemExit):
        auth.main(["set-google", "--stdin"])

    # settings edits go to the (temp) settings.json, keeping other sections
    config.SETTINGS_FILE.write_text(json.dumps({"language": "zh", "auth": {"trustedProxy": PROXY}}))
    assert auth.main(["allow-email", "New@Example.com"]) == 0
    assert auth.main(["allow-email", "new@example.com"]) == 0
    saved = json.loads(config.SETTINGS_FILE.read_text())
    assert saved["language"] == "zh"
    assert saved["auth"]["googleAllowedEmails"] == ["new@example.com"]
    with pytest.raises(SystemExit):
        auth.main(["allow-email", "nope"])
    assert auth.main(["deny-email", "NEW@example.com"]) == 0
    assert json.loads(config.SETTINGS_FILE.read_text())["auth"]["googleAllowedEmails"] == []

    with pytest.raises(SystemExit):
        auth.main(["set-public-url", "http://manga.example.org"])
    with pytest.raises(SystemExit):
        auth.main(["set-public-url", "https://manga.example.org/app"])
    assert auth.main(["set-public-url", "https://Manga.Example.org/"]) == 0
    a = json.loads(config.SETTINGS_FILE.read_text())["auth"]
    assert a["publicUrl"] == "https://manga.example.org"
    assert a["allowedHosts"] == ["manga.example.org"]
    assert auth.main(["set-public-url", "https://manga.example.org"]) == 0
    assert json.loads(config.SETTINGS_FILE.read_text())["auth"]["allowedHosts"] \
        == ["manga.example.org"]

    capsys.readouterr()
    assert auth.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "google client:    configured" in out and "https://manga.example.org" in out
    assert CSECRET not in out and CID not in out

    assert auth.main(["clear-google"]) == 0
    assert auth.google_credentials() is None
    assert auth.load_auth() is None          # no password and no Google: not configured


def test_cli_refuses_corrupt_settings(isolated):
    config.SETTINGS_FILE.write_text("{not json")
    with pytest.raises(SystemExit):
        auth.main(["allow-email", OWNER])
    assert config.SETTINGS_FILE.read_text() == "{not json"


def test_cli_deny_last_email_with_password_login_off(isolated):
    config.SETTINGS_FILE.write_text(json.dumps(
        {"auth": {"passwordLogin": False, "googleAllowedEmails": [OWNER]}}))
    with pytest.raises(SystemExit):
        auth.main(["deny-email", OWNER])
    assert json.loads(config.SETTINGS_FILE.read_text())["auth"]["googleAllowedEmails"] == [OWNER]
