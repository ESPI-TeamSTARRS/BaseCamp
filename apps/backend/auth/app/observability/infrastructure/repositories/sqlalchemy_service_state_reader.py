from datetime import datetime

from sqlalchemy import Column, DateTime, Engine, MetaData, String, Table, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.observability.domain.entities.service_state import ServiceState
from app.observability.domain.interfaces.service_state_reader import ServiceStateReader

# Table du verrouillage (migration 0009), vue ici par les seules colonnes utiles : aucune
# dependance vers la tranche `lockout`.
LOGIN_LOCKOUTS = Table(
    "login_lockouts",
    MetaData(),
    Column("scope", String(32)),
    Column("locked_until", DateTime(timezone=True)),
)


class SqlAlchemyServiceStateReader(ServiceStateReader):
    """Lit les verrous actifs en base a chaque collecte (aucun etat en memoire, partage entre instances).

    Une base indisponible ne leve pas : la lecture renvoie `None` et la collecte l'affiche par
    `auth_state_up 0`.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read(self, now: datetime) -> ServiceState | None:
        statement = (
            select(LOGIN_LOCKOUTS.c.scope, func.count())
            .where(LOGIN_LOCKOUTS.c.locked_until > now)
            .group_by(LOGIN_LOCKOUTS.c.scope)
        )
        try:
            with self._engine.connect() as connection:
                rows = connection.execute(statement).all()
        except SQLAlchemyError:
            return None
        return ServiceState({str(scope): int(count) for scope, count in rows})
