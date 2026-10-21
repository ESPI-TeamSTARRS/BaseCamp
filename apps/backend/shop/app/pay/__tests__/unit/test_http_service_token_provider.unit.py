import json

import httpx
import pytest

from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError
from app.pay.infrastructure.clients.http_service_token_provider import HttpServiceTokenProvider

URL = "http://auth:8000/internal/token"
SECRET = "client-secret-" + "x" * 20


class Auth:
    """Faux `auth` : emet des jetons numerotes, ou echoue."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.issued = 0
        self.status = 200
        self.lifetime: object = 300
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("auth arrete")
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "nope"})
        self.issued += 1
        return httpx.Response(
            200,
            json={
                "access_token": f"jeton-{self.issued}",
                "token_type": "Bearer",
                "expires_in": self.lifetime,
                "scope": "payments:write",
            },
        )


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _provider(auth: Auth, clock: Clock) -> HttpServiceTokenProvider:
    return HttpServiceTokenProvider(
        httpx.Client(transport=httpx.MockTransport(auth)),
        URL,
        "shop",
        SECRET,
        "payment",
        "payments:write",
        renew_margin_seconds=30,
        clock=clock,
    )


class TestObtainAndCache:
    def test_it_asks_auth_with_the_client_credentials_for_payment(self) -> None:
        auth = Auth()

        _provider(auth, Clock()).token()

        request = auth.requests[0]
        assert (request.method, str(request.url)) == ("POST", URL)
        assert json.loads(request.content) == {
            "grant_type": "client_credentials",
            "client_id": "shop",
            "client_secret": SECRET,
            "audience": "payment",
            "scope": "payments:write",
        }

    def test_the_token_is_reused_until_close_to_expiry(self) -> None:
        auth, clock = Auth(), Clock()
        provider = _provider(auth, clock)

        first = provider.token()
        clock.now += 200

        assert provider.token() == first
        assert len(auth.requests) == 1

    def test_the_token_is_renewed_before_it_expires(self) -> None:
        auth, clock = Auth(), Clock()
        provider = _provider(auth, clock)
        provider.token()

        clock.now += 280  # reste 20 s < marge de 30 s

        assert provider.token() == "jeton-2"

    def test_a_discarded_token_is_replaced(self) -> None:
        provider = _provider(Auth(), Clock())
        first = provider.token()

        provider.discard(first)

        assert provider.token() == "jeton-2"

    def test_discarding_another_token_keeps_the_current_one(self) -> None:
        provider = _provider(Auth(), Clock())
        current = provider.token()

        provider.discard("jeton-ancien")

        assert provider.token() == current


class TestWhenAuthFails:
    def test_no_token_ever_is_unavailable(self) -> None:
        auth = Auth()
        auth.down = True

        with pytest.raises(PaymentUnavailableError):
            _provider(auth, Clock()).token()

    @pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
    def test_a_refusal_of_auth_is_unavailable(self, status: int) -> None:
        auth = Auth()
        auth.status = status

        with pytest.raises(PaymentUnavailableError):
            _provider(auth, Clock()).token()

    @pytest.mark.parametrize("lifetime", [0, -5, "abc", None])
    def test_a_nonsense_lifetime_is_unavailable(self, lifetime: object) -> None:
        auth = Auth()
        auth.lifetime = lifetime

        with pytest.raises(PaymentUnavailableError):
            _provider(auth, Clock()).token()

    def test_a_still_valid_token_serves_when_renewal_fails(self) -> None:
        auth, clock = Auth(), Clock()
        provider = _provider(auth, clock)
        first = provider.token()
        clock.now += 280
        auth.down = True

        assert provider.token() == first

    def test_an_expired_token_is_not_served_when_renewal_fails(self) -> None:
        auth, clock = Auth(), Clock()
        provider = _provider(auth, clock)
        provider.token()
        clock.now += 400
        auth.down = True

        with pytest.raises(PaymentUnavailableError):
            provider.token()

    def test_the_secret_never_appears_in_the_error(self) -> None:
        auth = Auth()
        auth.status = 401

        with pytest.raises(PaymentUnavailableError) as raised:
            _provider(auth, Clock()).token()

        assert SECRET not in repr(raised.value)
