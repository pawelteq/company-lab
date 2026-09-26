from pathlib import Path
from alembic import op

revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None


def upgrade():
    op.execute((Path(__file__).parents[1]/'sql'/'0003_panel.sql').read_text(encoding='utf-8'))


def downgrade():
    raise RuntimeError('Forward-only: preserve published analytical snapshots')
