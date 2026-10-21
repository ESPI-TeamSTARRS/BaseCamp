from sqlalchemy import Engine, create_engine

from app.core.config import Settings

POOL_RECYCLE_SECONDS = 1800


def build_engine(settings: Settings) -> Engine:
    """Moteur Postgres à ressources bornées : pool, délais de connexion et de requête.

    `hide_parameters` garde les valeurs liées hors des messages d'erreur et donc des logs.
    """
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=POOL_RECYCLE_SECONDS,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": settings.db_connect_timeout_seconds,
            "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
        },
    )
