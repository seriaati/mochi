"""keni dates at midnight UTC

Income used to be sent at midnight in the saved timezone, which Keni can show as the day
before. Forgetting each synced row's date makes the next sync send it again, at midnight UTC.

Revision ID: 8e3f6a2b5d17
Revises: 4b7e2d9a1c03
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8e3f6a2b5d17'
down_revision: Union[str, Sequence[str], None] = '4b7e2d9a1c03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('UPDATE keni_links SET paid_on = NULL WHERE keni_id IS NOT NULL')


def downgrade() -> None:
    """Downgrade schema."""
