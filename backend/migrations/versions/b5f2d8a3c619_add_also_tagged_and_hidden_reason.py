"""add also_tagged and hidden_reason to crises

One article tagged with several countries used to become several pins. The duplicates are now
merged into one story (services/stories.py) and `also_tagged` keeps the other countries it was
tagged with. `hidden_reason` records why an event with a junk title (a bare site name or domain,
or the feed's "Conflict-related event in ..." stand-in) was hidden, so it is reversible.

Revision ID: b5f2d8a3c619
Revises: a9c3e5b7d142
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b5f2d8a3c619'
down_revision: Union[str, None] = 'a9c3e5b7d142'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crises', sa.Column('also_tagged', sa.Text(), nullable=True))
    op.add_column('crises', sa.Column('hidden_reason', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('crises', 'hidden_reason')
    op.drop_column('crises', 'also_tagged')
