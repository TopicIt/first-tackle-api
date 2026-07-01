from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.profile import PlayerProfile
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.profile import ProfileResponse


def token_response(user: User) -> TokenResponse:
    return TokenResponse(
        accessToken=create_access_token(user.id),
        refreshToken=create_refresh_token(user.id),
    )


def register_user(db: Session, payload: RegisterRequest) -> TokenResponse:
    email = payload.email.lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

    user = User(email=email, password_hash=hash_password(payload.password))
    profile = PlayerProfile(
        user=user,
        display_name=payload.display_name or email.split("@")[0],
        language="uk",
    )
    user.mark_login()
    db.add(user)
    db.add(profile)
    db.commit()
    db.refresh(user)
    return token_response(user)


def login_user(db: Session, payload: LoginRequest) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if user.disabled_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    user.mark_login()
    db.add(user)
    db.commit()
    return token_response(user)


def refresh_user_tokens(db: Session, refresh_token: str) -> TokenResponse:
    payload = decode_token(refresh_token, settings.jwt_refresh_secret, "refresh")
    user = db.get(User, payload["sub"])
    if user is None or user.disabled_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return token_response(user)


def profile_to_response(user: User) -> ProfileResponse:
    profile = user.profile
    return ProfileResponse(
        id=profile.id,
        userId=user.id,
        email=user.email,
        displayName=profile.display_name,
        avatarId=profile.avatar_id,
        avatarCustomUrl=profile.avatar_custom_url,
        language=profile.language,
        selectedStarId=profile.selected_star_id,
        createdAt=profile.created_at,
        updatedAt=profile.updated_at,
    )

