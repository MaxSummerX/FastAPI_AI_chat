"""add_missing_invites_table

Revision ID: be3ec778db76
Revises: b67166532fd5
Create Date: 2026-01-14 16:37:19.215100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be3ec778db76'
down_revision: Union[str, Sequence[str], None] = 'b67166532fd5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Создаём таблицу invites если она не существует
    op.execute("""
        CREATE TABLE IF NOT EXISTS invites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code VARCHAR(32) NOT NULL UNIQUE,
            is_used BOOLEAN NOT NULL DEFAULT FALSE,
            used_by_user_id UUID,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            used_at TIMESTAMP WITH TIME ZONE
        )
    """)

    # Создаём индекс
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_invites_code ON invites (code)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Удаляем индекс
    op.execute("DROP INDEX IF EXISTS ix_invites_code")

    # Удаляем таблицу
    op.execute("DROP TABLE IF EXISTS invites")
