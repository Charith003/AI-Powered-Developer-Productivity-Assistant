from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, stored: str) -> bool:
    return password_hash.verify(password, stored)


def create_access_token(user_id: str) -> tuple[str, int]:
    lifetime = timedelta(minutes=settings.access_token_minutes)
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": user_id, "type": "access", "iat": now, "exp": now + lifetime},
        settings.jwt_secret,
        algorithm="HS256",
    )
    return token, int(lifetime.total_seconds())


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    jti = str(uuid4())
    expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_days)
    token = jwt.encode(
        {
            "sub": user_id,
            "type": "refresh",
            "jti": jti,
            "iat": datetime.now(UTC),
            "exp": expires,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return token, jti, expires


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
