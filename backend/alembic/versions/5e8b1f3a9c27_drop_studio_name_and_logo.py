"""drop studio name and logo

Revision ID: 5e8b1f3a9c27
Revises: d2a7c4e19f60
Create Date: 2026-10-26 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e8b1f3a9c27'
down_revision: Union[str, Sequence[str], None] = 'd2a7c4e19f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. The app is Mochi everywhere now, with no studio name or logo."""
    op.drop_column('app_settings', 'studio_logo')
    op.drop_column('app_settings', 'studio_name')


def downgrade() -> None:
    """Downgrade schema. The old name and logo don't come back."""
    op.add_column('app_settings', sa.Column('studio_name', sa.String(length=60), nullable=True))
    op.add_column('app_settings', sa.Column('studio_logo', sa.Text(), nullable=True))
