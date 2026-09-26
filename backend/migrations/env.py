from alembic import context
from sqlalchemy import create_engine, pool
from etl.config import database_url


url = database_url(admin=True).replace('postgresql://','postgresql+psycopg://',1)
if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url,poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
