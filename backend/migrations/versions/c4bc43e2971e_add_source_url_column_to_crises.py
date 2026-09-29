"""add source_url column to crises

A real, structured link to the original source article/record — GDELT's
connector populates it from GDELT's own real SOURCEURL field, needed for
the lazy real-headline fetch (GDELTConnector.fetch_real_headline / the
GET /api/crises/<id>/real-headline endpoint) since GDELT's raw event
export has no article title/text at all (copyright reasons). Previously
NewsAPI-sourced crises already had a real URL, just overloaded into
source_id instead of a dedicated column.

Revision ID: c4bc43e2971e
Revises: e8201ea25035
Create Date: 2026-09-24 11:02:09.087709

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4bc43e2971e'
down_revision: Union[str, None] = 'e8201ea25035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crises', sa.Column('source_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('crises', 'source_url')
