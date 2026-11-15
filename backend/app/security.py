"""Password hashing and signed bearer-token helpers."""
import base64
import hashlib
import hmac
import json
import os
import time

from .config import SECRET_KEY, TOKEN_TTL_SECONDS

_PBKDF2_ROUNDS = 240_000
_SALT_BYTES = 16
_DIGEST_BYTES = 32


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return base64.urlsafe_b64encode(salt + digest).decode("ascii")


def verify_password(password: str, stored: str) -> bool:
    try:
        raw = base64.b64decode(stored.encode("ascii"), altchars=b"-_", validate=True)
        if len(raw) != _SALT_BYTES + _DIGEST_BYTES:
            return False
        salt, expected = raw[:_SALT_BYTES], raw[_SALT_BYTES:]
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError, AttributeError):
        return False


def create_token(user_id: int) -> str:
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    payload = {"sub": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def read_token(token: str) -> int | None:
    try:
        if not isinstance(token, str) or len(token) > 4096:
            return None
        body, signature = token.split(".", 1)
        if not body or len(signature) != 64:
            return None
        expected = hmac.new(SECRET_KEY.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        raw = base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        subject, expires = payload.get("sub"), payload.get("exp")
        if not isinstance(subject, int) or isinstance(subject, bool) or subject <= 0:
            return None
        if not isinstance(expires, int) or isinstance(expires, bool) or expires <= int(time.time()):
            return None
        return subject
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError, AttributeError):
        return None
