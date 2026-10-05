"""add story facts: article excerpt, extracted facts and when they were extracted

One small-model call per story reads the article excerpt and records the place,
casualty counts and scale cues (services/story_facts.py). The result is stored so
it is never extracted twice.

Revision ID: d4b7e9a1c836
Revises: c7e1b4a9d256
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4b7e9a1c836'
down_revision: Union[str, None] = 'c7e1b4a9d256'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crises', sa.Column('article_excerpt', sa.Text(), nullable=True))
    op.add_column('crises', sa.Column('facts', sa.Text(), nullable=True))
    op.add_column('crises', sa.Column('facts_extracted_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('crises', 'facts_extracted_at')
    op.drop_column('crises', 'facts')
    op.drop_column('crises', 'article_excerpt')
