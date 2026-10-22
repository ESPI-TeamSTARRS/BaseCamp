from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.backoffice.domain.entities.login_challenge import LoginChallenge
from app.backoffice.domain.interfaces.challenge_repository import ChallengeRepository
from app.backoffice.infrastructure.models.backoffice_challenge_model import (
    BackofficeChallengeModel,
)


class SqlAlchemyChallengeRepository(ChallengeRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, challenge: LoginChallenge) -> None:
        self._session.merge(
            BackofficeChallengeModel(
                digest=challenge.digest,
                account_id=challenge.account_id,
                email_hash=challenge.email_hash,
                address_hash=challenge.address_hash,
                expires_at=challenge.expires_at,
                face_ok=challenge.face_ok,
            )
        )
        self._session.flush()

    def take(self, digest: str, now: datetime) -> LoginChallenge | None:
        """Un seul DELETE ... RETURNING : de deux appels concurrents, un seul recoit la ligne."""
        statement = (
            delete(BackofficeChallengeModel)
            .where(BackofficeChallengeModel.digest == digest)
            .returning(BackofficeChallengeModel)
            .execution_options(populate_existing=True)
        )
        model = self._session.execute(statement).scalar_one_or_none()
        if model is None:
            return None
        challenge = LoginChallenge(
            model.digest,
            model.account_id,
            model.email_hash,
            model.address_hash,
            model.expires_at,
            model.face_ok,
        )
        return None if challenge.expired(now) else challenge

    def purge_expired(self, now: datetime) -> int:
        result = self._session.execute(
            delete(BackofficeChallengeModel).where(BackofficeChallengeModel.expires_at <= now)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]
