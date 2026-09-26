"""Immutable raw storage registry and company identity."""
from pathlib import Path
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).parents[1]/'sql'/'0001_raw_identity.sql').read_text(encoding='utf-8'))


def downgrade():
    raise RuntimeError('Forward-only migration: raw data must not be dropped by downgrade. Restore an explicitly selected backup instead.')
