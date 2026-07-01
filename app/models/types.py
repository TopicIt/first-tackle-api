from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB


JsonPayload = JSON().with_variant(JSONB(), "postgresql")
