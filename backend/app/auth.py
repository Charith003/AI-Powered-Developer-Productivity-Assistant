import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        401, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_token(credentials.credentials)
        if claims.get("type") != "access" or not claims.get("sub"):
            raise unauthorized
    except (jwt.InvalidTokenError, RuntimeError):
        raise unauthorized from None
    user = db.get(User, claims["sub"])
    if user is None or not user.is_active:
        raise unauthorized
    return user
