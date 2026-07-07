from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SaveMetadata(BaseModel):
    exists: bool
    save_version: int | None = Field(default=None, alias="saveVersion")
    revision: int | None = None
    checksum: str | None = None
    client_updated_at: datetime | None = Field(default=None, alias="clientUpdatedAt")
    server_updated_at: datetime | None = Field(default=None, alias="serverUpdatedAt")

    model_config = ConfigDict(populate_by_name=True)


class SaveSyncRequest(BaseModel):
    save_version: int = Field(alias="saveVersion")
    revision: int
    force: bool = False
    client_updated_at: datetime | None = Field(default=None, alias="clientUpdatedAt")
    checksum: str | None = None
    payload: dict[str, Any]

    model_config = ConfigDict(populate_by_name=True)


class SaveLoadResponse(BaseModel):
    metadata: SaveMetadata
    payload: dict[str, Any] | None = None


class SaveSyncResponse(BaseModel):
    metadata: SaveMetadata
