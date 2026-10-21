from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.password_reset.domain.interfaces.request_throttle import RequestThrottle
from app.password_reset.infrastructure.models.password_reset_attempt_model import (
    PasswordResetAttemptModel,
)


class SqlAlchemyRequestThrottle(RequestThrottle):
    """Fenetre glissante en base : l'etat survit aux redemarrages et se partage entre instances."""

    def __init__(self, session: Session, max_requests: int, window: timedelta) -> None:
        self._session = session
        self._max_requests = max_requests
        self._window = window

    def allow(self, fingerprint: str, now: datetime) -> bool:
        since = now - self._window
        self._session.execute(
            delete(PasswordResetAttemptModel).where(PasswordResetAttemptModel.requested_at < since)
        )
        recent = self._session.execute(
            select(func.count())
            .select_from(PasswordResetAttemptModel)
            .where(
                PasswordResetAttemptModel.email_fingerprint == fingerprint,
                PasswordResetAttemptModel.requested_at >= since,
            )
        ).scalar_one()
        if recent >= self._max_requests:
            return False
        self._session.add(
            PasswordResetAttemptModel(email_fingerprint=fingerprint, requested_at=now)
        )
        self._session.flush()
        return True
