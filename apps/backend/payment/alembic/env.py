from sqlalchemy import create_engine

from alembic import context
from app.confirmation.infrastructure.models import confirmation_key_model  # noqa: F401
from app.core.config import Settings
from app.intent.infrastructure.models import idempotency_key_model, payment_intent_model  # noqa: F401
from app.intent.infrastructure.models.base import Base
from app.ledger.infrastructure.models import ledger_entry_model  # noqa: F401
from app.ratelimit.infrastructure.models import rate_limit_window_model  # noqa: F401
from app.ratelimit.infrastructure.models.base import Base as RateLimitBase

target_metadata = [Base.metadata, RateLimitBase.metadata]


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
