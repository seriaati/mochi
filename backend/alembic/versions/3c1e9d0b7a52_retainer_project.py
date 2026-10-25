"""retainer project

Revision ID: 3c1e9d0b7a52
Revises: eac972b68f47
Create Date: 2026-10-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c1e9d0b7a52'
down_revision: Union[str, Sequence[str], None] = 'eac972b68f47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('retainers', sa.Column('project_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f('retainers_project_id_fkey'), 'retainers', 'projects', ['project_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('retainers_project_id_fkey'), 'retainers', type_='foreignkey')
    op.drop_column('retainers', 'project_id')
