"""add (is_active, scope, date_start) index to crises

The list endpoint filters on is_active (+ optionally scope) and a date_start
window; with tens of thousands of rows that was a full table scan on every
uncached request.

Revision ID: b7d2e41f9a35
Revises: a1f3c8d9e6b2
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7d2e41f9a35'
down_revision: Union[str, None] = 'a1f3c8d9e6b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_crises_active_scope_date',
        'crises',
        ['is_active', 'scope', 'date_start'],
    )


def downgrade() -> None:
    op.drop_index('ix_crises_active_scope_date', table_name='crises')
