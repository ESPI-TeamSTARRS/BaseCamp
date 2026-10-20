from sqlalchemy import create_engine

from alembic import context
from app.core.config import Settings

target_metadata = None  # les modeles SQLAlchemy s'ajouteront avec les tranches metier


def run_migrations_offline() -> None:
    context.configure(
        url=Settings().database_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(Settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
