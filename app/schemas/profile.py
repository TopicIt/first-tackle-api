from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProfileResponse(BaseModel):
    id: str
    user_id: str = Field(alias="userId")
    email: str
    display_name: str = Field(alias="displayName")
    avatar_id: str | None = Field(alias="avatarId")
    avatar_custom_url: str | None = Field(alias="avatarCustomUrl")
    language: str
    selected_star_id: str | None = Field(alias="selectedStarId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=80, alias="displayName")
    avatar_id: str | None = Field(default=None, max_length=80, alias="avatarId")
    avatar_custom_url: str | None = Field(default=None, max_length=500, alias="avatarCustomUrl")
    language: str | None = Field(default=None, max_length=12)
    selected_star_id: str | None = Field(default=None, max_length=80, alias="selectedStarId")

    model_config = ConfigDict(populate_by_name=True)

