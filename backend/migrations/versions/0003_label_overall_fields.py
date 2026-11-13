"""label format 2.0.0: most important thing to fix and a general comment

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("labelling_labels") as batch_op:
        batch_op.add_column(sa.Column("most_important_fix", sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column("general_comment", sa.Text(), nullable=False, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("labelling_labels") as batch_op:
        batch_op.drop_column("general_comment")
        batch_op.drop_column("most_important_fix")
