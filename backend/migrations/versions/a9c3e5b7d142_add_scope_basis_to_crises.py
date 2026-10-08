"""add scope_basis to crises

scope_basis: JSON text naming the rule and the list terms that made an event Global or Local
(services/scope.py). NULL means the event has not been judged by topic yet; start-up fills it in.

Revision ID: a9c3e5b7d142
Revises: e2a6c8d4f917
Create Date: 2026-10-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a9c3e5b7d142'
down_revision: Union[str, None] = 'e2a6c8d4f917'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crises', sa.Column('scope_basis', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('crises', 'scope_basis')
