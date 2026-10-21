from datetime import datetime

from sqlalchemy import Engine, text

from app.service_token.domain.entities.rate_limit_decision import RateLimitDecision
from app.service_token.domain.interfaces.rate_limiter import RateLimiter

WINDOW_SECONDS = 60

_COUNT_HIT = text(
    "INSERT INTO service_token_rate_limits (client_id, window_start, hits) "
    "VALUES (:client_id, :window_start, 1) "
    "ON CONFLICT (client_id, window_start) "
    "DO UPDATE SET hits = service_token_rate_limits.hits + 1 "
    "RETURNING hits"
)
_PURGE_OLD_WINDOWS = text(
    "DELETE FROM service_token_rate_limits WHERE window_start < :window_start"
)


class SqlAlchemyRateLimiter(RateLimiter):
    """Fenêtre fixe d'une minute par client, compteur dans la base d'auth (partagé, atomique).

    L'upsert `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` incrémente et lit le compteur en
    une seule instruction : deux instances d'auth ne perdent aucune demande. Aucun état en mémoire.
    """

    def __init__(self, engine: Engine, limit_per_window: int) -> None:
        self._engine = engine
        self._limit = limit_per_window

    def hit(self, client_id: str, now: datetime) -> RateLimitDecision:
        timestamp = int(now.timestamp())
        window_start = timestamp - timestamp % WINDOW_SECONDS
        with self._engine.begin() as connection:
            hits = connection.execute(
                _COUNT_HIT, {"client_id": client_id, "window_start": window_start}
            ).scalar_one()
            connection.execute(_PURGE_OLD_WINDOWS, {"window_start": window_start})
        retry_after = window_start + WINDOW_SECONDS - timestamp
        return RateLimitDecision(allowed=hits <= self._limit, retry_after_seconds=retry_after)
