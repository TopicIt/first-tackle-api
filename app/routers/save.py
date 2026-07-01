from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.save import SaveLoadResponse, SaveMetadata, SaveSyncRequest, SaveSyncResponse
from app.services.save_service import get_save_load, get_save_status, sync_save

router = APIRouter()


@router.get("/load", response_model=SaveLoadResponse)
def load_save(current_user: User = Depends(get_current_user)) -> SaveLoadResponse:
    return get_save_load(current_user)


@router.post("/sync", response_model=SaveSyncResponse)
def sync(
    payload: SaveSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SaveSyncResponse:
    return sync_save(db, current_user, payload)


@router.get("/status", response_model=SaveMetadata)
def save_status(current_user: User = Depends(get_current_user)) -> SaveMetadata:
    return get_save_status(current_user)

