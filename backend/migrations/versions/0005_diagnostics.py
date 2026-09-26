from pathlib import Path
from alembic import op
revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None


def upgrade():
    op.execute((Path(__file__).parents[1]/'sql'/'0005_diagnostics.sql').read_text(encoding='utf-8'))


def downgrade():
    raise RuntimeError('Forward-only: diagnostic records are immutable research provenance')
