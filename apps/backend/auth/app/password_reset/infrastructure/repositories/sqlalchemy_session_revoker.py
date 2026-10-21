from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, MetaData, Table, Uuid, delete
from sqlalchemy.orm import Session

from app.password_reset.domain.interfaces.session_revoker import SessionRevoker

# Table de la connexion (migration 0007), vue ici par sa seule colonne utile : aucune dependance
# vers la tranche `login`, et hors des metadonnees de l'inscription (aucune dérive de schema).
REFRESH_TOKENS = Table("refresh_tokens", MetaData(), Column("user_id", Uuid))


class SqlAlchemySessionRevoker(SessionRevoker):
    """Revoque les sessions en supprimant les jetons de rafraichissement du compte.

    Un jeton supprime est inconnu au rafraichissement : il est refuse. La suppression suit la
    transaction du changement de mot de passe (validee ou annulee avec lui).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def revoke_all(self, user_id: UUID, now: datetime) -> int:
        result = self._session.execute(
            delete(REFRESH_TOKENS).where(REFRESH_TOKENS.c.user_id == user_id)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]
