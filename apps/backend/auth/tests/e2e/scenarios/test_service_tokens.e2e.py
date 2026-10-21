"""Jetons de service sur la pile réelle.

`/internal/*` n'est joignable que sur le réseau interne `app` : depuis l'hôte, par la passerelle,
on doit obtenir 404. Les appels légitimes sont faits depuis le conteneur `shop` (réseau `app`)
avec `docker compose exec`, comme le fera un vrai appelant. Le secret du client `shop` vient de
AUTH_SERVICE_CLIENT_SECRET_SHOP (environnement ou .env).
"""

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.service_token.application.verify_token import VerifyTokenUseCase
from app.service_token.domain.entities.token_claims import TokenClaims
from app.service_token.domain.enums.token_use import TokenUse
from app.service_token.domain.exceptions.invalid_token_error import InvalidTokenError
from app.service_token.infrastructure.clients.ed25519_key_store import Ed25519KeyStore
from app.service_token.infrastructure.clients.jwt_token_decoder import JwtTokenDecoder
from app.service_token.infrastructure.clients.jwt_token_signer import JwtTokenSigner
from app.service_token.infrastructure.clients.system_clock import SystemClock

REPO_ROOT = Path(__file__).resolve().parents[6]
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
SHOP_ENV_VARIABLE = "AUTH_SERVICE_CLIENT_" + "SECRET_SHOP"  # nom de variable, pas une valeur
AUTH_URL = "http://auth:8000"
TOKEN_URL = f"{AUTH_URL}/internal/token"
JWKS_URL = f"{AUTH_URL}/.well-known/jwks.json"
# Exécuté dans le conteneur shop : N appels séquentiels, résultats en JSON (jamais le secret).
SCRIPT = """
import json, sys, urllib.request, urllib.error
url, count, body = sys.argv[1], int(sys.argv[2]), sys.argv[3]
results = []
for _ in range(count):
    request = urllib.request.Request(
        url, data=body.encode() if body else None,
        headers={"Content-Type": "application/json"}, method="POST" if body else "GET",
    )
    try:
        response = urllib.request.urlopen(request, timeout=10)
        results.append({"status": response.status, "headers": {k.lower(): v for k, v in response.headers.items()},
                        "body": json.load(response)})
    except urllib.error.HTTPError as error:
        results.append({"status": error.code, "headers": {k.lower(): v for k, v in error.headers.items()},
                        "body": json.loads(error.read() or "null")})
print(json.dumps(results))
"""


def _shop_secret() -> str:
    secret = os.environ.get(SHOP_ENV_VARIABLE)
    if secret:
        return secret
    for line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{SHOP_ENV_VARIABLE}="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{SHOP_ENV_VARIABLE} introuvable")


def _from_shop(
    url: str, body: dict[str, Any] | None = None, count: int = 1
) -> list[dict[str, Any]]:
    command = [
        "docker", "compose", "exec", "-T", "shop",
        "python", "-c", SCRIPT, url, str(count), json.dumps(body) if body else "",
    ]  # fmt: skip
    completed = subprocess.run(  # noqa: S603 - commande fixe, arguments maîtrisés par le test
        command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, check=True
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


def _request(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "grant_type": "client_credentials",
        "client_id": "shop",
        "client_secret": _shop_secret(),
        "audience": "payment",
        "scope": "payments:write",
    }
    body.update(overrides)
    return body


@pytest.fixture
def gateway() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=5.0, follow_redirects=True)


class TestInternalRoutesAreNotPublished:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/auth/internal/token",
            "/api/auth/internal/jwks",
            "/api/auth/%69nternal/token",
            "/api/auth//internal/token",
            "/internal/token",
        ],
    )
    def test_post_token_through_the_gateway_is_404(self, gateway: httpx.Client, path: str) -> None:
        response = gateway.post(path, json=_request())

        assert response.status_code == 404
        assert "access_token" not in response.text
        assert "invalid_client" not in response.text


class TestTokenIssuance:
    def test_shop_obtains_a_five_minute_token_for_payment_from_the_app_network(self) -> None:
        [response] = _from_shop(TOKEN_URL, _request())

        assert response["status"] == 200
        body = response["body"]
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == 300
        assert body["scope"] == "payments:write"
        assert response["headers"]["cache-control"] == "no-store"
        header = jwt.get_unverified_header(body["access_token"])
        assert header["alg"] == "EdDSA"

    def test_the_token_verifies_against_the_published_jwks(self) -> None:
        [issued] = _from_shop(TOKEN_URL, _request())
        [published] = _from_shop(JWKS_URL)
        token = issued["body"]["access_token"]
        [jwk] = published["body"]["keys"]

        claims = jwt.decode(
            token,
            jwt.PyJWK(jwk).key,
            algorithms=["EdDSA"],
            audience="payment",
            issuer="basecamp-auth",
        )

        assert jwt.get_unverified_header(token)["kid"] == jwk["kid"]
        assert claims["sub"] == "shop"
        assert claims["scope"] == "payments:write"
        assert claims["token_use"] == "service"
        assert claims["exp"] - claims["iat"] == 300
        assert abs(claims["iat"] - time.time()) < 60

    def test_unknown_client_and_bad_secret_get_identical_401s(self) -> None:
        [unknown] = _from_shop(TOKEN_URL, _request(client_id=f"ghost-{uuid.uuid4().hex[:8]}"))
        [bad_secret] = _from_shop(TOKEN_URL, _request(client_secret="x" * 40))

        assert unknown["status"] == bad_secret["status"] == 401
        assert unknown["body"] == bad_secret["body"] == {"error": "invalid_client"}
        assert unknown["headers"].keys() == bad_secret["headers"].keys()

    @pytest.mark.parametrize(
        "overrides",
        [{"scope": "payments:read"}, {"audience": "shop"}, {"audience": "unknown"}],
    )
    def test_scope_or_audience_not_granted_is_a_generic_401(
        self, overrides: dict[str, str]
    ) -> None:
        [response] = _from_shop(TOKEN_URL, _request(**overrides))

        assert response["status"] == 401
        assert response["body"] == {"error": "invalid_client"}


class TestRateLimitPerClient:
    def test_a_flooding_client_gets_429_while_shop_keeps_its_token(self) -> None:
        flooder = f"flood-{uuid.uuid4().hex[:8]}"

        # 125 demandes : même à cheval sur deux fenêtres d'une minute, l'une dépasse la limite (60).
        results = _from_shop(TOKEN_URL, _request(client_id=flooder), count=125)

        statuses = [result["status"] for result in results]
        assert statuses[0] == 401
        assert 429 in statuses
        limited = next(result for result in results if result["status"] == 429)
        assert limited["body"] == {"error": "rate_limited"}
        assert 1 <= int(limited["headers"]["retry-after"]) <= 60
        [shop] = _from_shop(TOKEN_URL, _request())
        assert shop["status"] == 200


class TestCrossUseRefusal:
    """Jeton réel émis par la pile, vérifié avec le vérificateur d'auth et les clés montées."""

    @staticmethod
    def _verifier(use: TokenUse) -> VerifyTokenUseCase:
        keys = Ed25519KeyStore(
            str(REPO_ROOT / ".secrets/auth/jwt-private.pem"),
            str(REPO_ROOT / ".secrets/auth/jwt-public.pem"),
        )
        return VerifyTokenUseCase(
            JwtTokenDecoder(keys),
            SystemClock(),
            use,
            "basecamp-auth",
            InMemoryBusinessEventLogger(),
        )

    def test_a_real_service_token_is_accepted_as_service_and_refused_as_client(self) -> None:
        [issued] = _from_shop(TOKEN_URL, _request())
        token = issued["body"]["access_token"]

        claims = self._verifier(TokenUse.SERVICE).execute(token, "payment", "payments:write")

        assert claims.subject == "shop"
        with pytest.raises(InvalidTokenError):
            self._verifier(TokenUse.CLIENT).execute(token, "payment")

    def test_a_client_token_forged_with_the_same_key_is_refused_as_service_token(self) -> None:
        keys = Ed25519KeyStore(
            str(REPO_ROOT / ".secrets/auth/jwt-private.pem"),
            str(REPO_ROOT / ".secrets/auth/jwt-public.pem"),
        )
        now = int(time.time())
        forged = JwtTokenSigner(keys).sign(
            TokenClaims("shop", "payment", frozenset({"payments:write"}), "basecamp-auth",
                        now, now + 300, "forged", TokenUse.CLIENT)
        )  # fmt: skip

        with pytest.raises(InvalidTokenError):
            self._verifier(TokenUse.SERVICE).execute(forged, "payment", "payments:write")
