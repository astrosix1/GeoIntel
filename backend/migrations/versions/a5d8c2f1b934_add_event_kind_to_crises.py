"""add event_kind to crises, backfill it, and hide the invented sample rows

event_kind: 'statement' (talks, criticism, threats: no physical site) or
'physical' (it happened somewhere), NULL when unknown.

Backfill: GDELT rows carry their CAMEO code in `analysis` ("CAMEO 112"), so
existing rows are classified from it (the rule is copied here on purpose so the
migration stays self-contained). ACLED rows are physical incidents.

The "Sample Data" rows were invented events that an earlier ACLED fallback saved
into the database on every sync. They are deactivated (kept, not deleted).
downgrade() drops the column but cannot re-activate them.

Revision ID: a5d8c2f1b934
Revises: f3c9a1d7e502
Create Date: 2026-10-04 00:00:00.000000

"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a5d8c2f1b934'
down_revision: Union[str, None] = 'f3c9a1d7e502'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATEMENT_ROOTS = {'10', '11', '12', '13', '16'}
_PHYSICAL_ROOTS = {'14', '15', '17', '18', '19', '20'}
_CAMEO = re.compile(r'CAMEO (\d{2,4})')
_BATCH = 500


def _kind(code):
    if len(code) < 2:
        return None
    if code[:2] in _STATEMENT_ROOTS or code.startswith('172'):
        return 'statement'
    if code[:2] in _PHYSICAL_ROOTS:
        return 'physical'
    return None


def upgrade() -> None:
    op.add_column('crises', sa.Column('event_kind', sa.String(length=12), nullable=True))

    bind = op.get_bind()
    crises = sa.table(
        'crises',
        sa.column('id', sa.String),
        sa.column('source', sa.String),
        sa.column('analysis', sa.Text),
        sa.column('event_kind', sa.String),
        sa.column('is_active', sa.Boolean),
    )

    by_kind = {'statement': [], 'physical': []}
    for crisis_id, analysis in bind.execute(sa.select(crises.c.id, crises.c.analysis).where(crises.c.source == 'GDELT')):
        match = _CAMEO.search(analysis or '')
        kind = _kind(match.group(1)) if match else None
        if kind:
            by_kind[kind].append(crisis_id)

    for kind, ids in by_kind.items():
        for start in range(0, len(ids), _BATCH):
            bind.execute(crises.update().where(crises.c.id.in_(ids[start:start + _BATCH])).values(event_kind=kind))

    bind.execute(crises.update().where(crises.c.source == 'ACLED').values(event_kind='physical'))
    bind.execute(crises.update().where(crises.c.source == 'Sample Data').values(is_active=False))


def downgrade() -> None:
    op.drop_column('crises', 'event_kind')
