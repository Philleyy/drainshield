"""
main.py: the DrainShield web server (FastAPI)

Run on your laptop (from the web/ folder):   python -m uvicorn server.main:app --reload
The React site is served from server/static (built with `npm run build` in web/frontend).

Everything under /api is JSON. Signed-in pages use the ds_session cookie; the sensor bridges use an
upload key instead (Authorization: Bearer dsk_...).
"""

from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, insert, select, update

from . import config, ingest, security
from .db import as_utc, create_tables, engine, ingest_keys, users, utcnow

ROLES = ("admin", "engineering", "crew", "demo")


@asynccontextmanager
async def lifespan(_app):
    create_tables()
    yield


app = FastAPI(title="DrainShield", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


# ---------------------------------------------------------------------------- safety on every response
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob: https://*.basemaps.cartocdn.com "
       "https://geo.weather.gc.ca; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


@app.middleware("http")
async def guard(request: Request, call_next):
    # A browser sends Origin on cross-site requests: refuse state changes coming from another site.
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path != "/api/ingest":
        origin = request.headers.get("origin")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        if origin and urlparse(origin).netloc != host:
            return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Content-Security-Policy", CSP)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def db():
    with engine.begin() as conn:            # one transaction per request: all or nothing
        yield conn


def is_https(request: Request) -> bool:
    if config.COOKIE_SECURE in ("1", "true", "yes"):
        return True
    if config.COOKIE_SECURE in ("0", "false", "no"):
        return False
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def set_session_cookie(request: Request, response: Response, token: str, max_age: int | None):
    response.set_cookie(config.SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=is_https(request),
                        samesite="lax", path="/")


def public_user(u) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"], "active": u["active"],
            "must_change_password": u["must_change_password"],
            "last_login_at": as_utc(u["last_login_at"]).isoformat() if u["last_login_at"] else None}


# ---------------------------------------------------------------------------- who is signed in
def _session_user(request: Request, conn, allow_pending_password: bool):
    u = security.user_for_session(conn, request.cookies.get(config.SESSION_COOKIE))
    if u is None:
        raise HTTPException(401, "Please sign in.")
    if u["must_change_password"] and not allow_pending_password:
        raise HTTPException(403, "password_change_required")
    return u


def current_user(request: Request, conn=Depends(db)):
    """Signed in, with a password of their own (not a temporary one)."""
    return _session_user(request, conn, allow_pending_password=False)


def signed_in_any(request: Request, conn=Depends(db)):
    """Signed in, possibly still on a temporary password (may only see /me and change it)."""
    return _session_user(request, conn, allow_pending_password=True)


def admin_user(u=Depends(current_user)):
    if u["role"] != "admin":
        raise HTTPException(403, "Administrators only.")
    return u


# ---------------------------------------------------------------------------- request bodies
class Email(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        v = v.strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@") or " " in v:
            raise ValueError("Enter a valid email address.")
        return v


class LoginBody(Email):
    password: str = Field(min_length=1, max_length=200)
    remember: bool = False


class SetupBody(Email):
    token: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class PasswordBody(BaseModel):
    current: str = Field(min_length=1, max_length=200)
    new: str = Field(min_length=1, max_length=200)


class NewUserBody(Email):
    name: str = Field(min_length=1, max_length=120)
    role: Literal["admin", "engineering", "crew", "demo"]


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Literal["admin", "engineering", "crew", "demo"] | None = None
    active: bool | None = None


class KeyBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


# ---------------------------------------------------------------------------- health + first-run setup
@app.get("/api/health")
def health(conn=Depends(db)):
    n = conn.execute(select(func.count()).select_from(users)).scalar_one()
    return {"ok": True, "database": engine.dialect.name, "accounts": n > 0}


def no_accounts(conn) -> bool:
    return conn.execute(select(func.count()).select_from(users)).scalar_one() == 0


@app.get("/api/setup")
def setup_status(conn=Depends(db)):
    return {"needed": no_accounts(conn) and bool(config.SETUP_TOKEN)}


@app.post("/api/setup")
def setup(body: SetupBody, request: Request, response: Response, conn=Depends(db)):
    if not no_accounts(conn):
        raise HTTPException(409, "Setup is already done. Sign in instead.")
    if not security.setup_token_ok(body.token):
        raise HTTPException(403, "This setup link is not valid.")
    if (p := security.password_problem(body.password)):
        raise HTTPException(422, p)
    uid = conn.execute(insert(users).values(email=body.email, name=body.name.strip(), role="admin",
                                            password_hash=security.hash_password(body.password), active=True,
                                            must_change_password=False, created_at=utcnow(),
                                            last_login_at=utcnow())).inserted_primary_key[0]
    token, max_age = security.create_session(conn, uid, True, request.headers.get("user-agent", ""))
    set_session_cookie(request, response, token, max_age)
    return {"ok": True}


# ---------------------------------------------------------------------------- sign in / out
@app.post("/api/auth/login")
def login(body: LoginBody, request: Request, response: Response, conn=Depends(db)):
    ip = client_ip(request)
    if security.limiter.blocked(body.email, ip):
        raise HTTPException(429, f"Too many attempts. Try again in {config.LOGIN_WINDOW_MIN} minutes.")
    u = conn.execute(select(users).where(users.c.email == body.email)).mappings().first()
    ok = security.verify_password(u["password_hash"] if u else None, body.password)
    if not ok or not u["active"]:
        security.limiter.failed(body.email, ip)
        raise HTTPException(401, "Wrong email or password.")
    security.limiter.succeeded(body.email)
    conn.execute(update(users).where(users.c.id == u["id"]).values(last_login_at=utcnow()))
    token, max_age = security.create_session(conn, u["id"], body.remember, request.headers.get("user-agent", ""))
    set_session_cookie(request, response, token, max_age)
    return {"user": public_user(u)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, conn=Depends(db)):
    security.end_session(conn, request.cookies.get(config.SESSION_COOKIE))
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(u=Depends(signed_in_any)):
    return {"user": public_user(u)}


@app.post("/api/auth/password")
def change_password(body: PasswordBody, request: Request, u=Depends(signed_in_any), conn=Depends(db)):
    if not security.verify_password(u["password_hash"], body.current):
        raise HTTPException(400, "Your current password is not right.")
    if (p := security.password_problem(body.new)):
        raise HTTPException(422, p)
    if body.new == body.current:
        raise HTTPException(422, "Choose a password different from the current one.")
    conn.execute(update(users).where(users.c.id == u["id"])
                 .values(password_hash=security.hash_password(body.new), must_change_password=False))
    security.end_all_sessions(conn, u["id"], keep_token=request.cookies.get(config.SESSION_COOKIE))
    return {"ok": True}


# ---------------------------------------------------------------------------- accounts (administrators)
@app.get("/api/users")
def list_users(_a=Depends(admin_user), conn=Depends(db)):
    return {"users": [public_user(u) for u in conn.execute(select(users).order_by(users.c.email)).mappings()]}


@app.post("/api/users")
def create_user(body: NewUserBody, _a=Depends(admin_user), conn=Depends(db)):
    if conn.execute(select(users.c.id).where(users.c.email == body.email)).first():
        raise HTTPException(409, "An account with this email already exists.")
    temp = security.temporary_password()
    uid = conn.execute(insert(users).values(email=body.email, name=body.name.strip(), role=body.role,
                                            password_hash=security.hash_password(temp), active=True,
                                            must_change_password=True, created_at=utcnow())).inserted_primary_key[0]
    u = conn.execute(select(users).where(users.c.id == uid)).mappings().first()
    return {"user": public_user(u), "temporary_password": temp}


def _other_active_admins(conn, uid):
    return conn.execute(select(func.count()).select_from(users).where(
        users.c.role == "admin", users.c.active.is_(True), users.c.id != uid)).scalar_one()


@app.patch("/api/users/{uid}")
def edit_user(uid: int, body: UserPatch, a=Depends(admin_user), conn=Depends(db)):
    u = conn.execute(select(users).where(users.c.id == uid)).mappings().first()
    if u is None:
        raise HTTPException(404, "No such account.")
    losing_admin = (body.role not in (None, "admin") or body.active is False) and u["role"] == "admin"
    if losing_admin and _other_active_admins(conn, uid) == 0:
        raise HTTPException(409, "Keep at least one active administrator.")
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    if values:
        conn.execute(update(users).where(users.c.id == uid).values(**values))
    if body.active is False:
        security.end_all_sessions(conn, uid)
    return {"user": public_user(conn.execute(select(users).where(users.c.id == uid)).mappings().first())}


@app.post("/api/users/{uid}/reset-password")
def reset_password(uid: int, _a=Depends(admin_user), conn=Depends(db)):
    if conn.execute(select(users.c.id).where(users.c.id == uid)).first() is None:
        raise HTTPException(404, "No such account.")
    temp = security.temporary_password()
    conn.execute(update(users).where(users.c.id == uid)
                 .values(password_hash=security.hash_password(temp), must_change_password=True))
    security.end_all_sessions(conn, uid)
    return {"temporary_password": temp}


# ---------------------------------------------------------------------------- sensor upload keys (administrators)
@app.get("/api/keys")
def list_keys(_a=Depends(admin_user), conn=Depends(db)):
    rows = conn.execute(select(ingest_keys).order_by(ingest_keys.c.created_at.desc())).mappings()
    return {"keys": [{"id": r["id"], "name": r["name"], "revoked": r["revoked"],
                      "created_at": as_utc(r["created_at"]).isoformat(),
                      "last_used_at": as_utc(r["last_used_at"]).isoformat() if r["last_used_at"] else None}
                     for r in rows]}


@app.post("/api/keys")
def create_key(body: KeyBody, a=Depends(admin_user), conn=Depends(db)):
    return {"key": security.new_ingest_key(conn, body.name.strip(), a["id"])}


@app.delete("/api/keys/{key_id}")
def revoke_key(key_id: str, _a=Depends(admin_user), conn=Depends(db)):
    n = conn.execute(update(ingest_keys).where(ingest_keys.c.id == key_id).values(revoked=True)).rowcount
    if not n:
        raise HTTPException(404, "No such key.")
    return {"ok": True}


# ---------------------------------------------------------------------------- sensor data
@app.post("/api/ingest")
def upload_readings(body: ingest.Upload, request: Request, conn=Depends(db)):
    if security.check_ingest_key(conn, request.headers.get("authorization")) is None:
        raise HTTPException(401, "Missing or wrong upload key.")
    return ingest.store(conn, body)


@app.get("/api/sensors")
def sensor_list(_u=Depends(current_user), conn=Depends(db)):
    return {"sensors": ingest.latest(conn), "now": utcnow().isoformat()}


@app.get("/api/sensors/{basin_id}/readings")
def sensor_readings(basin_id: str, limit: int = 200, _u=Depends(current_user), conn=Depends(db)):
    return {"readings": ingest.recent(conn, basin_id, max(1, min(limit, 2000)))}


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_not_found(rest: str):
    raise HTTPException(404, "Not found.")


# ---------------------------------------------------------------------------- the website itself
if (config.STATIC_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def site(path: str):
    """Every page of the React site is index.html; React shows the right screen for the address."""
    candidate = (config.STATIC_DIR / path).resolve()
    if path and candidate.is_file() and config.STATIC_DIR.resolve() in candidate.parents:
        return FileResponse(candidate)
    index = config.STATIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"app": "DrainShield", "note": "Front end not built yet (npm run build in web/frontend)."})
