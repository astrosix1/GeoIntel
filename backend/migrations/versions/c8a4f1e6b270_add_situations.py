"""add situations: grouped stories about one developing event

A situation links stories that tell the same event in different words (services/situations.py).
Nothing is merged or deleted: `crises.situation_id` points at the situation (the id of its lead
story) and the `situations` table holds the group's summary figures.

Revision ID: c8a4f1e6b270
Revises: b5f2d8a3c619
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c8a4f1e6b270'
down_revision: Union[str, None] = 'b5f2d8a3c619'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'situations',
        sa.Column('id', sa.String(length=50), primary_key=True),
        sa.Column('title', sa.String(length=200)),
        sa.Column('country', sa.String(length=100)),
        sa.Column('story_count', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('source_total', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('first_at', sa.DateTime()),
        sa.Column('last_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )
    op.add_column('crises', sa.Column('situation_id', sa.String(length=50), nullable=True))
    op.create_index('ix_crises_situation_id', 'crises', ['situation_id'])


def downgrade() -> None:
    op.drop_index('ix_crises_situation_id', table_name='crises')
    op.drop_column('crises', 'situation_id')
    op.drop_table('situations')
