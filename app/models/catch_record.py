import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.types import JsonPayload


class CatchRecord(Base):
    __tablename__ = "catch_records"
    __table_args__ = (
        UniqueConstraint("user_id", "catch_key", name="uq_catch_records_user_catch_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    catch_key: Mapped[str] = mapped_column(String(96), nullable=False)
    catch_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    fish_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    weight_grams: Mapped[int] = mapped_column(Integer, nullable=False)
    catch_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    trophy_tier: Mapped[str | None] = mapped_column(String(40), nullable=True)
    water_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bait_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tackle_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    depth: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cast_spot_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    caught_at_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caught_at_time: Mapped[str | None] = mapped_column(String(80), nullable=True)
    caught_at: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    raw_json: Mapped[dict[str, Any]] = mapped_column(JsonPayload, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="catch_records")
