"""
security.py: passwords, sign-in sessions, sensor upload keys and sign-in rate limiting

* Passwords are hashed with argon2id (the current recommendation); the database never holds a password.
* A session is a random 256-bit token in an HttpOnly cookie (JavaScript can't read it). The database stores
  only its sha256, so a leaked database can't be used to sign in.
* Sensor upload keys look like dsk_<id>_<secret>; only sha256(secret) is stored, and a key is shown once.
"""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import delete, insert, select, update

from . import config
from .db import as_utc, ingest_keys, sessions, users, utcnow

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("not-a-real-password-just-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Always runs one hash check, even for an unknown email, so timing doesn't reveal which emails exist."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problem(password: str) -> str | None:
    if len(password) < config.MIN_PASSWORD_LEN:
        return f"Use at least {config.MIN_PASSWORD_LEN} characters."
    if len(password) > 200:
        return "That password is too long."
    return None


def temporary_password() -> str:
    """Readable one-time password for a new account, e.g. 'k7Rp-2mXq-9vTa' (changed at first sign-in)."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------- sessions
def create_session(conn, user_id: int, remember: bool, user_agent: str) -> tuple[str, int | None]:
    """Returns (cookie value, cookie max-age in seconds or None for a browser-session cookie)."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    life = timedelta(days=config.REMEMBER_DAYS) if remember else timedelta(hours=config.SESSION_HOURS)
    conn.execute(insert(sessions).values(token_hash=_sha256(token), user_id=user_id, created_at=now,
                                         expires_at=now + life, last_seen_at=now, user_agent=user_agent[:255]))
    conn.execute(delete(sessions).where(sessions.c.expires_at < now))           # tidy up old ones
    return token, int(life.total_seconds()) if remember else None


def user_for_session(conn, token: str | None):
    """The signed-in, active user for this cookie, or None."""
    if not token or len(token) > 100:
        return None
    row = conn.execute(
        select(users, sessions.c.expires_at, sessions.c.last_seen_at)
        .join(sessions, sessions.c.user_id == users.c.id)
        .where(sessions.c.token_hash == _sha256(token))).mappings().first()
    if row is None or not row["active"] or as_utc(row["expires_at"]) < utcnow():
        return None
    now = utcnow()
    if now - as_utc(row["last_seen_at"]) > timedelta(minutes=5):                # don't write on every request
        conn.execute(update(sessions).where(sessions.c.token_hash == _sha256(token)).values(last_seen_at=now))
    return row


def end_session(conn, token: str | None):
    if token:
        conn.execute(delete(sessions).where(sessions.c.token_hash == _sha256(token)))


def end_all_sessions(conn, user_id: int, keep_token: str | None = None):
    q = delete(sessions).where(sessions.c.user_id == user_id)
    if keep_token:
        q = q.where(sessions.c.token_hash != _sha256(keep_token))
    conn.execute(q)


# ---------------------------------------------------------------------------- sensor upload keys
def new_ingest_key(conn, name: str, created_by: int) -> str:
    key_id = secrets.token_hex(4)
    secret = secrets.token_urlsafe(24)
    conn.execute(insert(ingest_keys).values(id=key_id, name=name, secret_hash=_sha256(secret),
                                            created_at=utcnow(), created_by=created_by, revoked=False))
    return f"dsk_{key_id}_{secret}"


def check_ingest_key(conn, header: str | None) -> str | None:
    """'Bearer dsk_<id>_<secret>' -> the key id if valid, else None."""
    if not header or not header.startswith("Bearer dsk_"):
        return None
    try:
        key_id, secret = header[len("Bearer dsk_"):].split("_", 1)
    except ValueError:
        return None
    row = conn.execute(select(ingest_keys).where(ingest_keys.c.id == key_id)).mappings().first()
    if row is None or row["revoked"] or not hmac.compare_digest(row["secret_hash"], _sha256(secret)):
        return None
    conn.execute(update(ingest_keys).where(ingest_keys.c.id == key_id).values(last_used_at=utcnow()))
    return key_id


# ---------------------------------------------------------------------------- sign-in rate limit
class LoginLimiter:
    """At most LOGIN_MAX_FAILS failed sign-ins per email and per IP in LOGIN_WINDOW_MIN minutes.
    Kept in memory (the app runs as one process); a restart forgets it, which is acceptable."""

    def __init__(self):
        self.fails = defaultdict(deque)

    def _recent(self, key):
        q = self.fails[key]
        cutoff = time.monotonic() - config.LOGIN_WINDOW_MIN * 60
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def blocked(self, email: str, ip: str) -> bool:
        return any(len(self._recent(k)) >= config.LOGIN_MAX_FAILS for k in (("e", email), ("i", ip)))

    def failed(self, email: str, ip: str):
        for k in (("e", email), ("i", ip)):
            self._recent(k).append(time.monotonic())

    def succeeded(self, email: str):
        self.fails.pop(("e", email), None)


limiter = LoginLimiter()


def setup_token_ok(given: str) -> bool:
    return bool(config.SETUP_TOKEN) and hmac.compare_digest(given.encode(), config.SETUP_TOKEN.encode())
