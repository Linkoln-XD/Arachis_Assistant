"""empty initial

Revision ID: 07d57758e633
Revises:
Create Date: 2026-10-11 16:05:52.455022

"""

from collections.abc import Sequence

revision: str = "07d57758e633"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
