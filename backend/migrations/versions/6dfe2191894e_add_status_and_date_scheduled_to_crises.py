"""add status and date_scheduled to crises

Vital-events expansion: elections and referendums are known in advance,
unlike every other crisis type (which is detected reactively from news
after the fact). date_scheduled holds that real future date; status
distinguishes a scheduled event that hasn't happened yet ('upcoming') from
an 'active' or 'resolved' one. date_start is left untouched and continues
to mean "when this row was ingested" for every row, including scheduled
ones — see the comment on Crisis.date_scheduled in models.py for why.

server_default='active' (not just the ORM-level Python default) is used
for `status` so the NOT NULL constraint succeeds against existing rows
without a separate data-backfill pass.

Revision ID: 6dfe2191894e
Revises: 2d71f4fa039c
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa

revision = '6dfe2191894e'
down_revision = '2d71f4fa039c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('crises', sa.Column('date_scheduled', sa.DateTime(), nullable=True))
    op.add_column('crises', sa.Column(
        'status', sa.String(length=20), nullable=False, server_default='active'
    ))
    op.create_index(op.f('ix_crises_status'), 'crises', ['status'])


def downgrade() -> None:
    op.drop_index(op.f('ix_crises_status'), table_name='crises')
    op.drop_column('crises', 'status')
    op.drop_column('crises', 'date_scheduled')
