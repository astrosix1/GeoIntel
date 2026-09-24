"""add region column to actors

Real world-region grouping for each actor (North America, Europe, East
Asia, etc.), populated in data_sources.init_actors(). This is what
analyze_cascade()'s affected_regions field needed — it previously always
returned [] because Actor had no region column at all, so the `hasattr`
check guarding it was always False.

Revision ID: e8201ea25035
Revises: 35c29d83a6e7
Create Date: 2026-09-23 22:34:41.639229

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8201ea25035'
down_revision: Union[str, None] = '35c29d83a6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('actors', sa.Column('region', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('actors', 'region')
