from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.profile import ProfileResponse, ProfileUpdateRequest
from app.services.auth_service import profile_to_response

router = APIRouter()


@router.get("/me", response_model=ProfileResponse)
def get_me(current_user: User = Depends(get_current_user)) -> ProfileResponse:
    return profile_to_response(current_user)


@router.patch("/me", response_model=ProfileResponse)
def update_me(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    profile = current_user.profile
    update = payload.model_dump(exclude_unset=True)
    for field, value in update.items():
        setattr(profile, field, value)
    db.add(profile)
    db.commit()
    db.refresh(current_user)
    return profile_to_response(current_user)

