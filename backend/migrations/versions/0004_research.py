from pathlib import Path
from alembic import op
revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None

def upgrade():
    op.execute((Path(__file__).parents[1]/'sql'/'0004_research.sql').read_text(encoding='utf-8'))

def downgrade():
    raise RuntimeError('Forward-only: research runs are reproducible immutable records')
