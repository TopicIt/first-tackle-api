from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.leaderboard_service import get_leaderboard

router = APIRouter()


@router.get("/species/{fish_id}/biggest")
def species_biggest(fish_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_leaderboard(db, "biggest-fish", fish_id=fish_id)


@router.get("/total-fish")
def total_fish(db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_leaderboard(db, "total-fish")


@router.get("/{board_type}")
def leaderboard(board_type: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_leaderboard(db, board_type)
