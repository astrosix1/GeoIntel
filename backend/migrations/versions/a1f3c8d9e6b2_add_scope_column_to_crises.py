"""add scope column to crises

A real classification, not geography: 'local' means small-scale,
non-geopolitical content (routine city/town crime, accidents,
human-interest stories) that GDELT's own CAMEO parser mis-tags as
conflict — the exact class of noise GDELTConnector._parse_row's
self-referential/demonym-self-referential actor-pair, generic-actor-name,
and blank-actor-under-violent-root signals were built and live-verified
to catch. Those signals now classify matching rows as scope='local'
instead of discarding them, so a real "Local" news toggle in the UI has
real content to show. Every existing row (all of ACLED/NewsAPI, and any
GDELT row that already passed every filter cleanly) defaults to
'global' — the safe, backward-compatible default.

Revision ID: a1f3c8d9e6b2
Revises: c4bc43e2971e
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f3c8d9e6b2'
down_revision: Union[str, None] = 'c4bc43e2971e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'crises',
        sa.Column('scope', sa.String(length=10), nullable=False, server_default='global'),
    )


def downgrade() -> None:
    op.drop_column('crises', 'scope')
