"""add location refinement columns to crises

location_refined_at: set when a definitive attempt to refine the pin from the
source article has finished (so it is never repeated, even after a restart).
location_refined_name: the specific place found; NULL with refined_at set means
"tried, no usable location".

Revision ID: f3c9a1d7e502
Revises: b7d2e41f9a35
Create Date: 2026-10-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f3c9a1d7e502'
down_revision: Union[str, None] = 'b7d2e41f9a35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crises', sa.Column('location_refined_at', sa.DateTime(), nullable=True))
    op.add_column('crises', sa.Column('location_refined_name', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('crises', 'location_refined_name')
    op.drop_column('crises', 'location_refined_at')
