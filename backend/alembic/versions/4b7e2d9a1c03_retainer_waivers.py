"""retainer waivers

Revision ID: 4b7e2d9a1c03
Revises: 5e8b1f3a9c27
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b7e2d9a1c03'
down_revision: Union[str, Sequence[str], None] = '5e8b1f3a9c27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'retainer_waivers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('retainer_id', sa.Integer(), nullable=False),
        sa.Column('period', sa.Date(), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['retainer_id'], ['retainers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('retainer_id', 'period'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('retainer_waivers')
