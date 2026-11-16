"""Add optional dataset source (admin-only provenance).

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("labelling_batches") as batch_op:
        batch_op.add_column(sa.Column("source", sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("labelling_batches") as batch_op:
        batch_op.drop_column("source")
