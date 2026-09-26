"""Typed financial staging, relationship snapshots and import diagnostics."""
from pathlib import Path
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).parents[1]/'sql'/'0002_staging.sql').read_text(encoding='utf-8'))


def downgrade():
    raise RuntimeError('Forward-only: preserve financial staging and evidence.')
