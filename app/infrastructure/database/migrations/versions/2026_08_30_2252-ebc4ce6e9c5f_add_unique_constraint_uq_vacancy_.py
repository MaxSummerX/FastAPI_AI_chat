"""add unique constraint uq_vacancy_analysis_user_vacancy_type

Revision ID: ebc4ce6e9c5f
Revises: 6ec10bf7ad0a
Create Date: 2026-08-30 22:52:24.021129

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ebc4ce6e9c5f"
down_revision: str | Sequence[str] | None = "6ec10bf7ad0a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        "uq_vacancy_analysis_user_vacancy_type",
        "vacancy_analyses",
        ["user_id", "vacancy_id", "analysis_type"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_vacancy_analysis_user_vacancy_type", "vacancy_analyses", type_="unique")
