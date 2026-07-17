"""persistent catch records

Revision ID: 0002_persistent_catch_records
Revises: 0001_initial_schema
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_persistent_catch_records"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "catch_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("catch_key", sa.String(length=96), nullable=False),
        sa.Column("catch_id", sa.String(length=96), nullable=True),
        sa.Column("fish_id", sa.String(length=80), nullable=False),
        sa.Column("weight_grams", sa.Integer(), nullable=False),
        sa.Column("catch_category", sa.String(length=40), nullable=True),
        sa.Column("trophy_tier", sa.String(length=40), nullable=True),
        sa.Column("water_id", sa.String(length=80), nullable=True),
        sa.Column("bait_id", sa.String(length=80), nullable=True),
        sa.Column("method", sa.String(length=80), nullable=True),
        sa.Column("tackle_summary", sa.String(length=255), nullable=True),
        sa.Column("depth", sa.String(length=40), nullable=True),
        sa.Column("cast_spot_id", sa.String(length=80), nullable=True),
        sa.Column("caught_at_day", sa.Integer(), nullable=True),
        sa.Column("caught_at_time", sa.String(length=80), nullable=True),
        sa.Column("caught_at", sa.String(length=120), nullable=True),
        sa.Column("source_revision", sa.Integer(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("raw_json", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "catch_key", name="uq_catch_records_user_catch_key"),
    )
    op.create_index("ix_catch_records_user_id", "catch_records", ["user_id"])
    op.create_index("ix_catch_records_catch_id", "catch_records", ["catch_id"])
    op.create_index("ix_catch_records_fish_id", "catch_records", ["fish_id"])


def downgrade() -> None:
    op.drop_index("ix_catch_records_fish_id", table_name="catch_records")
    op.drop_index("ix_catch_records_catch_id", table_name="catch_records")
    op.drop_index("ix_catch_records_user_id", table_name="catch_records")
    op.drop_table("catch_records")
