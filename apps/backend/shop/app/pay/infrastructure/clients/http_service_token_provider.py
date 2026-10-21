import time
from collections.abc import Callable
from threading import Lock

import httpx

from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError
from app.pay.domain.interfaces.service_token_provider import ServiceTokenProvider

HTTP_OK = 200


class HttpServiceTokenProvider(ServiceTokenProvider):
    """Obtient, garde et renouvelle le jeton de service aupres de `auth` (`POST /internal/token`).

    Le jeton est court (quelques minutes) et ne vit qu'en memoire : il n'est ni journalise ni
    persiste. Il est renouvele `renew_margin_seconds` avant son expiration; si `auth` ne repond pas
    a ce moment, le jeton encore valide continue de servir. Sans jeton valide, `PaymentUnavailableError`
    (la boutique repond 503 proprement, sans bloquer).
    """

    def __init__(
        self,
        client: httpx.Client,
        url: str,
        client_id: str,
        client_secret: str,
        audience: str,
        scope: str,
        renew_margin_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._url = url
        self._credentials = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": audience,
            "scope": scope,
        }
        self._margin = renew_margin_seconds
        self._clock = clock
        self._lock = Lock()
        self._token: str | None = None
        self._expires_at = 0.0

    def token(self) -> str:
        with self._lock:
            now = self._clock()
            if self._token is not None and now < self._expires_at - self._margin:
                return self._token
            try:
                return self._renew(now)
            except PaymentUnavailableError:
                if self._token is not None and now < self._expires_at:
                    return self._token  # encore valide : on ne casse pas les paiements pour autant
                self._token = None
                raise

    def discard(self, token: str) -> None:
        with self._lock:
            if self._token == token:
                self._token = None

    def _renew(self, now: float) -> str:
        try:
            response = self._client.post(
                self._url, json=self._credentials, headers={"Accept": "application/json"}
            )
            if response.status_code != HTTP_OK:
                raise PaymentUnavailableError
            body = response.json()
            token = str(body["access_token"])
            lifetime = float(body["expires_in"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise PaymentUnavailableError from None
        if not token or lifetime <= 0:
            raise PaymentUnavailableError
        self._token = token
        self._expires_at = now + lifetime
        return token
