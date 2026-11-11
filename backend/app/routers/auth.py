from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import RefreshToken, User
from app.schemas import (
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    TokenResponse,
    UserProfile,
)
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def issue_tokens(db: Session, user: User) -> TokenResponse:
    access, ttl = create_access_token(user.id)
    refresh, jti, expires = create_refresh_token(user.id)
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=expires))
    db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=ttl)


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = str(payload.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    name = payload.full_name.strip()
    if not name:
        raise HTTPException(422, "Full name cannot be blank")
    user = User(email=email, full_name=name, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.flush()
        return issue_tokens(db, user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists") from None


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(401, "Email or password is incorrect")
    return issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: dict[str, str], db: Session = Depends(get_db)) -> TokenResponse:
    try:
        claims = decode_token(payload.get("refresh_token", ""))
        if claims.get("type") != "refresh":
            raise ValueError
        record = db.get(RefreshToken, claims.get("jti", ""))
        if (
            record is None
            or record.revoked
            or record.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC)
        ):
            raise ValueError
        user = db.get(User, record.user_id)
        if user is None or not user.is_active:
            raise ValueError
    except (jwt.InvalidTokenError, ValueError, TypeError, RuntimeError):
        raise HTTPException(401, "Invalid or expired refresh token") from None
    record.revoked = True
    return issue_tokens(db, user)


@router.post("/logout", status_code=204)
def logout(payload: dict[str, str], db: Session = Depends(get_db)) -> None:
    try:
        claims = decode_token(payload.get("refresh_token", ""))
        record = db.get(RefreshToken, claims.get("jti", ""))
        if claims.get("type") == "refresh" and record:
            record.revoked = True
            db.commit()
    except (jwt.InvalidTokenError, RuntimeError):
        pass


@router.get("/me", response_model=UserProfile)
def get_profile(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserProfile)
def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    name = payload.full_name.strip()
    if not name:
        raise HTTPException(422, "Full name cannot be blank")
    user.full_name = name
    db.commit()
    db.refresh(user)
    return user
