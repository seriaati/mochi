"""fcm tokens

Revision ID: 288aa608b515
Revises: 2c9d4e7f1a35
Create Date: 2026-11-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '288aa608b515'
down_revision: Union[str, Sequence[str], None] = '2c9d4e7f1a35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('fcm_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('fcm_tokens')
