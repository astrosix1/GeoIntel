"""add crisis_snapshots table

A real time-series of severity readings, one row per active crisis per
scheduled sync run (see DataAggregator.snapshot_severity_history in
data_sources.py). analyze_escalation() in app.py previously fabricated a
"7-day trend" from a deterministic backward extrapolation of the single
current Crisis.severity value, since no real history existed anywhere —
this table is what makes that trend honest going forward. Crises won't
have real history immediately after this ships; analyze_escalation()
degrades to an explicit 'insufficient_data' result until at least 2
snapshots exist for a given crisis, rather than fabricating one.

Revision ID: 35c29d83a6e7
Revises: 6dfe2191894e
Create Date: 2026-09-23 20:41:25.557268

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35c29d83a6e7'
down_revision: Union[str, None] = '6dfe2191894e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'crisis_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('crisis_id', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.Integer(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_crisis_snapshots_crisis_id'), 'crisis_snapshots', ['crisis_id'])
    op.create_index(op.f('ix_crisis_snapshots_recorded_at'), 'crisis_snapshots', ['recorded_at'])
    op.create_index(
        'ix_crisis_snapshots_crisis_recorded', 'crisis_snapshots', ['crisis_id', 'recorded_at']
    )


def downgrade() -> None:
    op.drop_index('ix_crisis_snapshots_crisis_recorded', table_name='crisis_snapshots')
    op.drop_index(op.f('ix_crisis_snapshots_recorded_at'), table_name='crisis_snapshots')
    op.drop_index(op.f('ix_crisis_snapshots_crisis_id'), table_name='crisis_snapshots')
    op.drop_table('crisis_snapshots')
