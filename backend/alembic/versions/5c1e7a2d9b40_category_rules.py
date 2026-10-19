"""category rules

Revision ID: 5c1e7a2d9b40
Revises: 747f7042d952
Create Date: 2026-10-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5c1e7a2d9b40'
down_revision: Union[str, Sequence[str], None] = '747f7042d952'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'rules',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('rules_pkey')),
        sa.UniqueConstraint('name', name=op.f('rules_name_key')),
    )
    op.add_column('transactions', sa.Column('category_rule_id', sa.BigInteger(), nullable=True))
    op.create_index(op.f('transactions_category_rule_id_idx'), 'transactions', ['category_rule_id'], unique=False)
    op.create_foreign_key(
        op.f('transactions_category_rule_id_fkey'), 'transactions', 'rules', ['category_rule_id'], ['id'],
        ondelete='SET NULL',
    )
    op.drop_constraint(op.f('transactions_category_source_known_check'), 'transactions', type_='check')
    op.create_check_constraint(
        op.f('transactions_category_source_known_check'), 'transactions',
        "category_source in ('laya', 'jev', 'rule', 'manual')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('transactions_category_source_known_check'), 'transactions', type_='check')
    op.execute(
        "update transactions set category = null, category_source = null, category_confidence = null, "
        "categorised_at = null where category_source = 'rule'"
    )
    op.create_check_constraint(
        op.f('transactions_category_source_known_check'), 'transactions', "category_source in ('laya', 'jev', 'manual')"
    )
    op.drop_constraint(op.f('transactions_category_rule_id_fkey'), 'transactions', type_='foreignkey')
    op.drop_index(op.f('transactions_category_rule_id_idx'), table_name='transactions')
    op.drop_column('transactions', 'category_rule_id')
    op.drop_table('rules')
