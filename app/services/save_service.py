from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.game_save import GameSave
from app.models.user import User
from app.schemas.save import SaveLoadResponse, SaveMetadata, SaveSyncRequest, SaveSyncResponse


def save_metadata(game_save: GameSave | None) -> SaveMetadata:
    if game_save is None:
        return SaveMetadata(exists=False)
    return SaveMetadata(
        exists=True,
        saveVersion=game_save.save_version,
        revision=game_save.revision,
        checksum=game_save.checksum,
        clientUpdatedAt=game_save.client_updated_at,
        serverUpdatedAt=game_save.server_updated_at,
    )


def get_save_status(user: User) -> SaveMetadata:
    return save_metadata(user.game_save)


def get_save_load(user: User) -> SaveLoadResponse:
    game_save = user.game_save
    return SaveLoadResponse(
        metadata=save_metadata(game_save),
        payload=game_save.payload_json if game_save is not None else None,
    )


def sync_save(db: Session, user: User, payload: SaveSyncRequest) -> SaveSyncResponse:
    game_save = user.game_save
    if game_save is None:
        game_save = GameSave(
            user_id=user.id,
            save_version=payload.save_version,
            revision=1,
            payload_json=payload.payload,
            checksum=payload.checksum,
            client_updated_at=payload.client_updated_at,
        )
        db.add(game_save)
        db.commit()
        db.refresh(game_save)
        return SaveSyncResponse(metadata=save_metadata(game_save))

    if payload.revision != game_save.revision and not payload.force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Save revision conflict",
                "serverRevision": game_save.revision,
                "serverUpdatedAt": game_save.server_updated_at.isoformat() if game_save.server_updated_at else None,
                "clientRevision": payload.revision,
            },
        )

    game_save.save_version = payload.save_version
    game_save.revision += 1
    game_save.payload_json = payload.payload
    game_save.checksum = payload.checksum
    game_save.client_updated_at = payload.client_updated_at
    db.add(game_save)
    db.commit()
    db.refresh(game_save)
    return SaveSyncResponse(metadata=save_metadata(game_save))
