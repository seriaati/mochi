"""retainer payment months

Revision ID: 9b4f2e7c1d38
Revises: 3c1e9d0b7a52
Create Date: 2026-10-25 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b4f2e7c1d38'
down_revision: Union[str, Sequence[str], None] = '3c1e9d0b7a52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Existing payments cover one month each."""
    op.add_column(
        'retainer_payments', sa.Column('months', sa.Integer(), server_default='1', nullable=False)
    )
    op.create_check_constraint('months_positive', 'retainer_payments', 'months >= 1')


def downgrade() -> None:
    """Downgrade schema. A payment covering several months keeps only its first."""
    op.drop_constraint('months_positive', 'retainer_payments', type_='check')
    op.drop_column('retainer_payments', 'months')
