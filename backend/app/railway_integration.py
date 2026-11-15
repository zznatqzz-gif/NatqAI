"""Per-user encrypted Railway credential storage and remote identity validation."""
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken

from .config import SECRET_KEY


def _fernet() -> Fernet:
    # Derive a stable encryption key from the deployment secret; changing the
    # application secret intentionally makes stored credentials unreadable.
    digest = hashlib.sha256(("natqai-railway-token:" + SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError("Stored Railway credential cannot be decrypted; reconnect Railway.") from exc


async def railway_graphql(token: str, query: str, variables: dict | None = None) -> dict:
    """Execute a bounded Railway Public GraphQL request; never return credentials."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://backboard.railway.com/graphql/v2",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"query": query, "variables": variables or {}},
            )
        if response.status_code != 200:
            raise RuntimeError("Railway rejected the request")
        payload = response.json()
        if payload.get("errors") or not isinstance(payload.get("data"), dict):
            raise RuntimeError("Railway returned a GraphQL error")
        return payload["data"]
    except httpx.TimeoutException as exc:
        raise TimeoutError("Railway request timed out") from exc
    except httpx.RequestError as exc:
        raise ConnectionError("Could not reach Railway") from exc


def get_user_railway_token(user_id: int) -> str | None:
    from .db import connection
    with connection() as conn:
        row = conn.execute(
            "SELECT encrypted_secret FROM user_integrations WHERE user_id=? AND provider='railway'",
            (user_id,),
        ).fetchone()
    return decrypt_token(row["encrypted_secret"]) if row else None
