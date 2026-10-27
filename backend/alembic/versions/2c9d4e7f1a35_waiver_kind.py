"""waiver kind

Revision ID: 2c9d4e7f1a35
Revises: 8e3f6a2b5d17
Create Date: 2026-10-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2c9d4e7f1a35'
down_revision: Union[str, Sequence[str], None] = '8e3f6a2b5d17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# add_column doesn't create enum types, so the type is created once up front.
waiver_kind = postgresql.ENUM('waived', 'given_up', name='waiverkind', create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    waiver_kind.create(op.get_bind())
    # Existing waivers were all let off the fee.
    op.add_column(
        'retainer_waivers',
        sa.Column('kind', waiver_kind, server_default='waived', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('retainer_waivers', 'kind')
    waiver_kind.drop(op.get_bind())
