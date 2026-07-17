from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.catch_record import CatchRecordSyncRequest, CatchRecordSyncResponse
from app.services.catch_record_service import sync_catch_entries

router = APIRouter()


@router.post("/sync", response_model=CatchRecordSyncResponse)
def sync_catches(
    payload: CatchRecordSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CatchRecordSyncResponse:
    synced_ids, rejected = sync_catch_entries(
        db,
        current_user,
        payload.catches,
        source_revision=payload.source_revision,
        source_updated_at=payload.client_updated_at,
    )
    db.commit()
    return CatchRecordSyncResponse(
        syncedCatchIds=synced_ids,
        syncedCount=len(synced_ids),
        rejectedCount=len(rejected),
        rejected=rejected[:20],
        serverUpdatedAt=datetime.now(timezone.utc),
    )
