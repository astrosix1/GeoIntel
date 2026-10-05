"""add story merging: merged_into, source_count, and the merge-verdict cache

Duplicate and near-duplicate events are merged into one story instead of being
dropped (see services/stories.py). A merged duplicate is kept but set inactive
with `merged_into` pointing at the story's primary event, so it is reversible and
old ids still resolve. `source_count` is the number of distinct outlets behind
the story. `story_merge_checks` remembers each AI verdict on a borderline pair so
the same pair is never judged twice.

Revision ID: c7e1b4a9d256
Revises: a5d8c2f1b934
Create Date: 2026-10-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c7e1b4a9d256'
down_revision: Union[str, None] = 'a5d8c2f1b934'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crises', sa.Column('merged_into', sa.String(length=50), nullable=True))
    op.add_column('crises', sa.Column('source_count', sa.Integer(), nullable=False, server_default='1'))
    op.create_index('ix_crises_merged_into', 'crises', ['merged_into'])
    op.create_table(
        'story_merge_checks',
        sa.Column('pair_key', sa.String(length=120), primary_key=True),
        sa.Column('same_event', sa.Boolean(), nullable=False),
        sa.Column('checked_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('story_merge_checks')
    op.drop_index('ix_crises_merged_into', table_name='crises')
    op.drop_column('crises', 'source_count')
    op.drop_column('crises', 'merged_into')
