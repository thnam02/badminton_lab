"""batches become datasets: technique, number, due date, note; per-video capture context

Existing batches get their technique from their clips (else their upload
job) and a number per technique in creation order; no due date.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("labelling_batches") as batch_op:
        batch_op.add_column(sa.Column("technique", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("due_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("note", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("labelling_upload_job_clips") as batch_op:
        batch_op.add_column(sa.Column("handedness", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("camera_view", sa.String(length=20), nullable=True))

    from app.labelling.datasets import backfill_datasets

    backfill_datasets(op.get_bind())

    with op.batch_alter_table("labelling_batches") as batch_op:
        batch_op.create_unique_constraint(
            op.f("uq_labelling_batches_technique_number"), ["technique", "number"]
        )


def downgrade() -> None:
    with op.batch_alter_table("labelling_batches") as batch_op:
        batch_op.drop_constraint(op.f("uq_labelling_batches_technique_number"), type_="unique")
        batch_op.drop_column("note")
        batch_op.drop_column("due_date")
        batch_op.drop_column("number")
        batch_op.drop_column("technique")
    with op.batch_alter_table("labelling_upload_job_clips") as batch_op:
        batch_op.drop_column("camera_view")
        batch_op.drop_column("handedness")
