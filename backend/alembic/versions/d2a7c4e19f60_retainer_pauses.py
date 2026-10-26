"""retainer pauses

Revision ID: d2a7c4e19f60
Revises: 9b4f2e7c1d38
Create Date: 2026-10-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2a7c4e19f60'
down_revision: Union[str, Sequence[str], None] = '9b4f2e7c1d38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'retainer_pauses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('retainer_id', sa.Integer(), nullable=False),
        sa.Column('paused_on', sa.Date(), nullable=False),
        sa.Column('resumed_on', sa.Date(), nullable=True),
        sa.CheckConstraint('resumed_on IS NULL OR resumed_on > paused_on', name='resumed_after'),
        sa.ForeignKeyConstraint(['retainer_id'], ['retainers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('retainer_pauses')
