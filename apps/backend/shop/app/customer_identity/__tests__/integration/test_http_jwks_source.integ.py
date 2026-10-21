import httpx
import pytest

from app.customer_identity.__tests__.tokens import SigningKey
from app.customer_identity.domain.exceptions.verification_keys_unavailable_error import (
    VerificationKeysUnavailableError,
)
from app.customer_identity.infrastructure.clients.http_jwks_source import HttpJwksSource

URL = "http://auth:8000/.well-known/jwks.json"


def source(handler: httpx.MockTransport) -> HttpJwksSource:
    return HttpJwksSource(httpx.Client(transport=handler), URL)


class TestHttpJwksSource:
    def test_it_indexes_the_published_ed25519_keys_by_kid(self) -> None:
        first, second = SigningKey("a"), SigningKey("b")
        document = {"keys": [first.jwk, second.jwk, {"kty": "RSA", "kid": "c"}, {"kty": "OKP"}]}
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, json=document)

        keys = source(httpx.MockTransport(handler)).fetch()

        assert requested == [URL]
        assert dict(keys) == {"a": first.jwk, "b": second.jwk}

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(500),
            httpx.Response(404),
            httpx.Response(200, text="<html>"),
            httpx.Response(200, json={"autre": []}),
            httpx.Response(200, json={"keys": "pas une liste"}),
            httpx.Response(200, json=[]),
        ],
    )
    def test_a_failure_or_an_odd_document_is_an_unavailable_error(
        self, response: httpx.Response
    ) -> None:
        with pytest.raises(VerificationKeysUnavailableError):
            source(httpx.MockTransport(lambda request: response)).fetch()

    def test_a_network_failure_is_an_unavailable_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("auth arrete")

        with pytest.raises(VerificationKeysUnavailableError):
            source(httpx.MockTransport(handler)).fetch()
