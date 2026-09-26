from pathlib import Path
from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).parents[1] / 'sql' / '0006_profile_screening.sql').read_text(encoding='utf-8'))


def downgrade():
    raise RuntimeError('Forward-only: keep profile screening history')
