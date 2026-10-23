"""track from and per-client reminders

Revision ID: 669bb8775abc
Revises: 581acb90882d
Create Date: 2026-10-24 08:11:19.849938

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '669bb8775abc'
down_revision: Union[str, Sequence[str], None] = '581acb90882d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Retainers: track from the start month, so existing data keeps its meaning.
    op.add_column('retainers', sa.Column('tracked_from', sa.Date(), nullable=True))
    op.execute("UPDATE retainers SET tracked_from = date_trunc('month', started_on)::date")
    op.alter_column('retainers', 'tracked_from', existing_type=sa.Date(), nullable=False)

    # Reminder log: per client instead of per retainer month. Old rows map to their retainer's
    # client; manual pings, which had no slot, count for the day they were sent (UTC).
    op.add_column('reminder_log', sa.Column('client_id', sa.Integer(), nullable=True))
    op.execute(
        "UPDATE reminder_log l SET client_id = r.client_id FROM retainers r"
        " WHERE r.id = l.retainer_id"
    )
    op.execute("UPDATE reminder_log SET slot_on = (sent_at AT TIME ZONE 'UTC')::date WHERE slot_on IS NULL")
    op.alter_column('reminder_log', 'client_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('reminder_log', 'slot_on', existing_type=sa.DATE(), nullable=False)
    op.drop_constraint(op.f('reminder_log_retainer_id_period_slot_on_key'), 'reminder_log', type_='unique')
    op.drop_constraint(op.f('reminder_log_retainer_id_fkey'), 'reminder_log', type_='foreignkey')
    op.create_foreign_key(
        'reminder_log_client_id_fkey', 'reminder_log', 'clients', ['client_id'], ['id'], ondelete='CASCADE'
    )
    op.drop_column('reminder_log', 'period')
    op.drop_column('reminder_log', 'retainer_id')


def downgrade() -> None:
    """Downgrade schema. Per-client reminder history can't be split back into retainer months,
    so it is dropped."""
    op.drop_column('retainers', 'tracked_from')
    op.execute("DELETE FROM reminder_log")
    op.add_column('reminder_log', sa.Column('retainer_id', sa.INTEGER(), autoincrement=False, nullable=False))
    op.add_column('reminder_log', sa.Column('period', sa.DATE(), autoincrement=False, nullable=False))
    op.drop_constraint('reminder_log_client_id_fkey', 'reminder_log', type_='foreignkey')
    op.create_foreign_key(op.f('reminder_log_retainer_id_fkey'), 'reminder_log', 'retainers', ['retainer_id'], ['id'], ondelete='CASCADE')
    op.create_unique_constraint(op.f('reminder_log_retainer_id_period_slot_on_key'), 'reminder_log', ['retainer_id', 'period', 'slot_on'])
    op.alter_column('reminder_log', 'slot_on',
               existing_type=sa.DATE(),
               nullable=True)
    op.drop_column('reminder_log', 'client_id')
