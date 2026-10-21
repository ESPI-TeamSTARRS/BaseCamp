from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.password_reset.domain.interfaces.session_revoker import SessionRevoker
from app.password_reset.infrastructure.models.session_revocation_model import (
    SessionRevocationModel,
)


class SqlAlchemySessionRevoker(SessionRevoker):
    """Implementation minimale : un seuil de revocation par compte (table additive).

    La connexion et le rafraichissement (ticket suivant) refusent toute session emise avant
    `revoked_at`. Quand la table des jetons de rafraichissement existera, un adaptateur qui les
    revoque directement remplacera cette classe sans toucher au cas d'usage.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def revoke_all(self, user_id: UUID, now: datetime) -> None:
        self._session.merge(SessionRevocationModel(user_id=user_id, revoked_at=now))
        self._session.flush()
