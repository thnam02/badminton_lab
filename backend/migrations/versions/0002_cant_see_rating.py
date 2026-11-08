"""allow the "can't see" rating for coach-only questions

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "labelling_stat_labels"
NAME = "ck_labelling_stat_labels_rating_value"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint(op.f(NAME), type_="check")
        batch_op.create_check_constraint(
            "rating_value", "rating IN ('good', 'needs_work', 'looks_wrong', 'cant_see')"
        )


def downgrade() -> None:
    op.execute(f"UPDATE {TABLE} SET rating = NULL WHERE rating = 'cant_see'")
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint(op.f(NAME), type_="check")
        batch_op.create_check_constraint(
            "rating_value", "rating IN ('good', 'needs_work', 'looks_wrong')"
        )
