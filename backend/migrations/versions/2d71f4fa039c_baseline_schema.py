"""baseline schema

Snapshot of the schema as produced by models.py's Base.metadata.create_all()
prior to Alembic being introduced. This revision exists so:

  - a brand-new database can run `alembic upgrade head` instead of relying
    on create_all() (which can create tables but never alters them), and
  - an existing database (dev or production) that already has these tables
    can be marked as being at this point with `alembic stamp head`, without
    re-running the (already-applied) create_table statements.

Every future schema change should be its own migration generated with
`alembic revision --autogenerate -m "..."` against models.py, not a direct
edit to a table that's already live.

Revision ID: 2d71f4fa039c
Revises:
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa

revision = '2d71f4fa039c'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'crises',
        sa.Column('id', sa.String(length=50), primary_key=True),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('country', sa.String(length=100), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('severity', sa.Integer()),
        sa.Column('confidence', sa.Integer()),
        sa.Column('location_confidence', sa.Integer()),
        sa.Column('date_start', sa.DateTime()),
        sa.Column('date_updated', sa.DateTime()),
        sa.Column('analysis', sa.Text()),
        sa.Column('impact', sa.Text()),
        sa.Column('stakeholders', sa.String(length=500)),
        sa.Column('military_score', sa.Integer()),
        sa.Column('economic_score', sa.Integer()),
        sa.Column('political_score', sa.Integer()),
        sa.Column('environment_score', sa.Integer()),
        sa.Column('technology_score', sa.Integer()),
        sa.Column('information_score', sa.Integer()),
        sa.Column('source', sa.String(length=100)),
        sa.Column('source_id', sa.String(length=100)),
        sa.Column('is_active', sa.Boolean()),
        sa.Column('is_verified', sa.Boolean()),
    )

    op.create_table(
        'forecasts',
        sa.Column('id', sa.String(length=50), primary_key=True),
        sa.Column('crisis_id', sa.String(length=50), nullable=False),
        sa.Column('question', sa.String(length=300), nullable=False),
        sa.Column('prob_unlikely', sa.Integer()),
        sa.Column('prob_possible', sa.Integer()),
        sa.Column('prob_likely', sa.Integer()),
        sa.Column('confidence', sa.Integer()),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
        sa.Column('method', sa.String(length=100)),
        sa.Column('notes', sa.Text()),
    )

    op.create_table(
        'actors',
        sa.Column('id', sa.String(length=10), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50)),
        sa.Column('latitude', sa.Float()),
        sa.Column('longitude', sa.Float()),
        sa.Column('color', sa.String(length=7)),
        sa.Column('military_power', sa.Integer()),
        sa.Column('economic_power', sa.Integer()),
        sa.Column('political_influence', sa.Integer()),
        sa.Column('technological_capability', sa.Integer()),
        sa.Column('population', sa.Integer()),
        sa.Column('gdp', sa.Float()),
        sa.Column('is_nuclear', sa.Boolean()),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table(
        'relationships',
        sa.Column('id', sa.String(length=50), primary_key=True),
        sa.Column('actor_a', sa.String(length=10), nullable=False),
        sa.Column('actor_b', sa.String(length=10), nullable=False),
        sa.Column('type', sa.String(length=50)),
        sa.Column('label', sa.String(length=200)),
        sa.Column('strength', sa.Integer()),
        sa.Column('stability', sa.Integer()),
        sa.Column('is_active', sa.Boolean()),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table(
        'news',
        sa.Column('id', sa.String(length=100), primary_key=True),
        sa.Column('crisis_id', sa.String(length=50)),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('url', sa.String(length=500)),
        sa.Column('source', sa.String(length=100)),
        sa.Column('content', sa.Text()),
        sa.Column('published_at', sa.DateTime()),
        sa.Column('fetched_at', sa.DateTime()),
        sa.Column('sentiment', sa.String(length=20)),
        sa.Column('sentiment_score', sa.Float()),
    )

    op.create_table(
        'economic_data',
        sa.Column('id', sa.String(length=50), primary_key=True),
        sa.Column('country_code', sa.String(length=3), nullable=False),
        sa.Column('gdp', sa.Float()),
        sa.Column('gdp_growth', sa.Float()),
        sa.Column('exports', sa.Float()),
        sa.Column('imports', sa.Float()),
        sa.Column('inflation', sa.Float()),
        sa.Column('unemployment', sa.Float()),
        sa.Column('trade_balance', sa.Float()),
        sa.Column('foreign_reserves', sa.Float()),
        sa.Column('debt_to_gdp', sa.Float()),
        sa.Column('year', sa.Integer()),
        sa.Column('created_at', sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table('economic_data')
    op.drop_table('news')
    op.drop_table('relationships')
    op.drop_table('actors')
    op.drop_table('forecasts')
    op.drop_table('crises')
