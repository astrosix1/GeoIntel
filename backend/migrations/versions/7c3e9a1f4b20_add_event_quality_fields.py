"""add event quality fields and crisis_sources

Event quality pipeline, phase 5 (docs/EVENT_FILTERING.md): duplicate
reports of the same event are merged into one crises row instead of each
creating its own pin, with provenance kept in the new crisis_sources table.
The new crises columns carry what the pipeline establishes about each event
— full source URL, canonical country code (the frontend topojson's ISO
numeric id), location precision, number of merged sources, when a sync last
reported it (stale rows are deactivated), and the global-impact score with
its breakdown (phase 6). All nullable/defaulted, so existing rows are
untouched until scripts/reprocess_crises.py backfills them.

Revision ID: 7c3e9a1f4b20
Revises: e8201ea25035
Create Date: 2026-09-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c3e9a1f4b20'
down_revision: Union[str, None] = 'e8201ea25035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crises', sa.Column('source_url', sa.Text(), nullable=True))
    op.add_column('crises', sa.Column('country_code', sa.String(length=3), nullable=True))
    op.add_column('crises', sa.Column('location_precision', sa.String(length=10), nullable=True))
    op.add_column('crises', sa.Column('source_count', sa.Integer(), nullable=True, server_default='1'))
    op.add_column('crises', sa.Column('last_seen_at', sa.DateTime(), nullable=True))
    op.add_column('crises', sa.Column('global_impact', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('crises', sa.Column('scoring_factors', sa.Text(), nullable=True))
    op.create_index('ix_crises_active_country_date', 'crises', ['is_active', 'country_code', 'date_start'])
    op.create_index('ix_crises_last_seen_at', 'crises', ['last_seen_at'])

    op.create_table(
        'crisis_sources',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('crisis_id', sa.String(length=50), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('external_id', sa.String(length=100), nullable=True),
        sa.Column('url_key', sa.String(length=500), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('outlet', sa.String(length=100), nullable=True),
        sa.Column('title', sa.String(length=300), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('added_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('crisis_id', 'url_key', name='uq_crisis_sources_crisis_url'),
    )
    op.create_index('ix_crisis_sources_crisis_id', 'crisis_sources', ['crisis_id'])
    op.create_index('ix_crisis_sources_url_key', 'crisis_sources', ['url_key'])


def downgrade() -> None:
    op.drop_index('ix_crisis_sources_url_key', table_name='crisis_sources')
    op.drop_index('ix_crisis_sources_crisis_id', table_name='crisis_sources')
    op.drop_table('crisis_sources')
    op.drop_index('ix_crises_last_seen_at', table_name='crises')
    op.drop_index('ix_crises_active_country_date', table_name='crises')
    op.drop_column('crises', 'scoring_factors')
    op.drop_column('crises', 'global_impact')
    op.drop_column('crises', 'last_seen_at')
    op.drop_column('crises', 'source_count')
    op.drop_column('crises', 'location_precision')
    op.drop_column('crises', 'country_code')
    op.drop_column('crises', 'source_url')
