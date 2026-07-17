from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CatchRecordSyncRequest(BaseModel):
    catches: list[dict[str, Any]] = Field(default_factory=list)
    source_revision: int | None = Field(default=None, alias="sourceRevision")
    client_updated_at: datetime | None = Field(default=None, alias="clientUpdatedAt")

    model_config = ConfigDict(populate_by_name=True)


class CatchRecordSyncResponse(BaseModel):
    ok: bool = True
    synced_catch_ids: list[str] = Field(default_factory=list, alias="syncedCatchIds")
    synced_count: int = Field(default=0, alias="syncedCount")
    rejected_count: int = Field(default=0, alias="rejectedCount")
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    server_updated_at: datetime = Field(alias="serverUpdatedAt")

    model_config = ConfigDict(populate_by_name=True)
