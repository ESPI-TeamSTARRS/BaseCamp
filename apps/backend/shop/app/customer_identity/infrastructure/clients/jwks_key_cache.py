from collections.abc import Callable, Mapping
from threading import Lock
from typing import Any

from app.customer_identity.domain.exceptions.verification_keys_unavailable_error import (
    VerificationKeysUnavailableError,
)
from app.customer_identity.domain.interfaces.jwks_source import JwksSource


class JwksKeyCache:
    """Cles de verification d'`auth` gardees quelques minutes, relues sur `kid` inconnu.

    Ce n'est pas un etat metier : ce sont des cles PUBLIQUES, relisibles a tout moment (un
    redemarrage les relit). Regles :
    - une cle en cache sert tant qu'elle est fraiche (`ttl_seconds`);
    - une lecture echouee ne vide jamais le cache (les jetons deja emis restent verifiables si `auth`
      est arrete) : on garde les cles perimees plutot que de rejeter;
    - un `kid` inconnu declenche une relecture, au plus une toutes les `min_refetch_seconds`
      (un attaquant qui presente des `kid` au hasard ne peut pas marteler `auth`).
    """

    def __init__(
        self,
        source: JwksSource,
        clock: Callable[[], float],
        ttl_seconds: float = 300.0,
        min_refetch_seconds: float = 10.0,
    ) -> None:
        self._source = source
        self._clock = clock
        self._ttl = ttl_seconds
        self._min_refetch = min_refetch_seconds
        self._lock = Lock()
        self._keys: Mapping[str, Mapping[str, Any]] = {}
        self._fetched_at: float | None = None
        self._attempted_at: float | None = None

    def key_for(self, kid: str) -> Mapping[str, Any] | None:
        """Cle publiee pour ce `kid`, ou `None` si `auth` ne la publie pas.

        Leve `VerificationKeysUnavailableError` seulement si aucune cle n'est connue et que la
        lecture echoue.
        """
        with self._lock:
            now = self._clock()
            known = self._keys.get(kid)
            if known is not None and not self._stale(now):
                return known
            if self._may_refetch(now):
                self._refetch(now)
            if not self._keys and self._fetched_at is None:
                raise VerificationKeysUnavailableError
            return self._keys.get(kid)

    def _stale(self, now: float) -> bool:
        return self._fetched_at is None or now - self._fetched_at >= self._ttl

    def _may_refetch(self, now: float) -> bool:
        return self._attempted_at is None or now - self._attempted_at >= self._min_refetch

    def _refetch(self, now: float) -> None:
        self._attempted_at = now
        try:
            fetched = self._source.fetch()
        except VerificationKeysUnavailableError:
            return  # on garde les cles deja connues, meme perimees
        self._keys = dict(fetched)
        self._fetched_at = now
