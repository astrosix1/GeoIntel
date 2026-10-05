"""add strict severity columns: severity_level (1-5) and severity_basis (JSON reasons)

Severity is scored by code from extracted facts (services/severity.py); the basis
records the reasons shown under "Why this rating". Existing rows are rescored with
`python -m services.severity`.

Revision ID: e2a6c8d4f917
Revises: d4b7e9a1c836
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e2a6c8d4f917'
down_revision: Union[str, None] = 'd4b7e9a1c836'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crises', sa.Column('severity_level', sa.Integer(), nullable=True))
    op.add_column('crises', sa.Column('severity_basis', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('crises', 'severity_basis')
    op.drop_column('crises', 'severity_level')
