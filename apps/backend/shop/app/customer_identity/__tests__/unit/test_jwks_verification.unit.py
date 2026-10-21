from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import jwt
import pytest

from app.customer_identity.__tests__.tokens import AUDIENCE, ISSUER, SigningKey
from app.customer_identity.domain.exceptions.client_token_rejected_error import (
    ClientTokenRejectedError,
    TokenRejection,
)
from app.customer_identity.domain.exceptions.verification_keys_unavailable_error import (
    VerificationKeysUnavailableError,
)
from app.customer_identity.domain.interfaces.jwks_source import JwksSource
from app.customer_identity.infrastructure.clients.jwks_client_token_verifier import (
    JwksClientTokenVerifier,
)
from app.customer_identity.infrastructure.clients.jwks_key_cache import JwksKeyCache

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeJwks(JwksSource):
    def __init__(self, *keys: SigningKey) -> None:
        self.keys = {key.kid: key.jwk for key in keys}
        self.calls = 0
        self.down = False

    def fetch(self) -> Mapping[str, Mapping[str, Any]]:
        self.calls += 1
        if self.down:
            raise VerificationKeysUnavailableError
        return dict(self.keys)


class Clock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value


class Setup:
    def __init__(self, *keys: SigningKey) -> None:
        self.key = keys[0] if keys else SigningKey()
        self.source = FakeJwks(*(keys or (self.key,)))
        self.clock = Clock()
        self.cache = JwksKeyCache(self.source, self.clock, ttl_seconds=300, min_refetch_seconds=10)
        self.verifier = JwksClientTokenVerifier(self.cache, ISSUER, AUDIENCE)

    def verify(self, token: str, now: datetime = NOW) -> Any:
        return self.verifier.verify(token, now)


def issued_now(**kwargs: Any) -> dict[str, Any]:
    return {"issued_at": NOW.timestamp(), **kwargs}


class TestValidTokens:
    def test_a_token_of_auth_gives_the_customer_without_calling_auth_again(self) -> None:
        setup = Setup()
        token = setup.key.token(**issued_now())

        first = setup.verify(token)
        second = setup.verify(token)

        assert first.id == second.id
        assert first.email_verified is True
        assert setup.source.calls == 1  # une seule lecture du JWKS pour deux verifications

    def test_an_unverified_email_is_reported_as_such(self) -> None:
        setup = Setup()

        customer = setup.verify(setup.key.token(**issued_now(email_verified=False)))

        assert customer.email_verified is False

    def test_the_expiry_is_judged_with_a_thirty_second_tolerance(self) -> None:
        setup = Setup()
        token = setup.key.token(**issued_now(lifetime=900))

        assert setup.verify(token, NOW.replace(minute=15, second=29))
        with pytest.raises(ClientTokenRejectedError) as error:
            setup.verify(token, NOW.replace(minute=15, second=31))

        assert error.value.rejection is TokenRejection.EXPIRED


class TestRejectedTokens:
    @pytest.mark.parametrize(
        ("kwargs", "reason"),
        [
            ({"issuer": "autre-emetteur"}, TokenRejection.WRONG_ISSUER),
            ({"audience": "basecamp-service-api"}, TokenRejection.WRONG_AUDIENCE),
            ({"use": "service"}, TokenRejection.NOT_A_CLIENT_TOKEN),
            ({"drop": ("sub",)}, TokenRejection.INVALID),
            ({"drop": ("exp",)}, TokenRejection.INVALID),
            ({"extra": {"sub": "pas-un-uuid"}}, TokenRejection.INVALID),
            ({"extra": {"exp": "demain"}}, TokenRejection.INVALID),
        ],
    )
    def test_each_check_of_the_contract_refuses_with_its_own_internal_reason(
        self, kwargs: dict[str, Any], reason: TokenRejection
    ) -> None:
        setup = Setup()

        with pytest.raises(ClientTokenRejectedError) as error:
            setup.verify(setup.key.token(**issued_now(**kwargs)))

        assert error.value.rejection is reason

    def test_a_token_signed_by_another_key_with_a_published_kid_is_refused(self) -> None:
        setup = Setup()
        forger = SigningKey(kid=setup.key.kid)

        with pytest.raises(ClientTokenRejectedError) as error:
            setup.verify(forger.token(**issued_now()))

        assert error.value.rejection is TokenRejection.INVALID

    def test_a_token_without_kid_or_with_an_unpublished_kid_is_refused(self) -> None:
        setup = Setup()
        with pytest.raises(ClientTokenRejectedError) as unknown:
            setup.verify(SigningKey(kid="inconnu").token(**issued_now()))
        no_kid = jwt.encode({"sub": "x"}, "secret-de-test-assez-long-pour-hs256-0123", "HS256")
        with pytest.raises(ClientTokenRejectedError) as missing:
            setup.verify(no_kid)

        assert unknown.value.rejection is TokenRejection.UNKNOWN_KEY
        assert missing.value.rejection is TokenRejection.MISSING_KEY_ID

    @pytest.mark.parametrize("algorithm", ["HS256", "none"])
    def test_only_eddsa_is_accepted(self, algorithm: str) -> None:
        setup = Setup()
        forged = jwt.encode(
            {"sub": "x"},
            "secret-de-test-assez-long-pour-hs256-0123" if algorithm == "HS256" else "",
            algorithm=algorithm,
            headers={"kid": setup.key.kid},
        )

        with pytest.raises(ClientTokenRejectedError) as error:
            setup.verify(forged)

        assert error.value.rejection is TokenRejection.BAD_ALGORITHM

    @pytest.mark.parametrize(
        "garbage",
        ["", "pas.un.jeton", "a.b", "x" * 50, "W10.e30.sig", "bm9uLWpzb24.e30.sig", "a.b.c.d"],
    )
    def test_garbage_is_refused(self, garbage: str) -> None:
        setup = Setup()

        with pytest.raises(ClientTokenRejectedError) as error:
            setup.verify(garbage)

        assert error.value.rejection is TokenRejection.INVALID


class TestKeyCache:
    def test_a_fresh_key_is_served_from_the_cache(self) -> None:
        setup = Setup()
        setup.cache.key_for(setup.key.kid)
        setup.clock.value += 299

        setup.cache.key_for(setup.key.kid)

        assert setup.source.calls == 1

    def test_a_stale_key_is_refreshed(self) -> None:
        setup = Setup()
        setup.cache.key_for(setup.key.kid)
        setup.clock.value += 301

        setup.cache.key_for(setup.key.kid)

        assert setup.source.calls == 2

    def test_an_unknown_kid_triggers_a_refresh_and_a_rotated_key_is_found(self) -> None:
        setup = Setup()
        setup.cache.key_for(setup.key.kid)
        rotated = SigningKey(kid="kid-2")
        setup.source.keys[rotated.kid] = rotated.jwk
        setup.clock.value += 20

        assert setup.cache.key_for("kid-2") == rotated.jwk
        assert setup.source.calls == 2

    def test_random_kids_cannot_hammer_auth(self) -> None:
        setup = Setup()
        setup.cache.key_for(setup.key.kid)

        for index in range(50):
            assert setup.cache.key_for(f"inconnu-{index}") is None

        assert setup.source.calls <= 2  # au plus une relecture dans la fenetre de 10 s

    def test_an_auth_outage_keeps_serving_known_keys_even_stale(self) -> None:
        setup = Setup()
        token = setup.key.token(**issued_now())
        setup.verify(token)
        setup.source.down = True
        setup.clock.value += 10_000  # cles perimees, auth arrete

        assert setup.verify(token).id

    def test_with_no_key_ever_read_an_outage_is_reported_not_treated_as_a_refusal(self) -> None:
        setup = Setup()
        setup.source.down = True

        with pytest.raises(VerificationKeysUnavailableError):
            setup.verify(setup.key.token(**issued_now()))

    def test_the_outage_is_not_retried_more_than_once_per_window(self) -> None:
        setup = Setup()
        setup.source.down = True
        for _ in range(5):
            with pytest.raises(VerificationKeysUnavailableError):
                setup.cache.key_for("kid-1")

        assert setup.source.calls == 1

    def test_the_cache_recovers_once_auth_answers_again(self) -> None:
        setup = Setup()
        setup.source.down = True
        with pytest.raises(VerificationKeysUnavailableError):
            setup.cache.key_for("kid-1")
        setup.source.down = False
        setup.clock.value += 11

        assert setup.cache.key_for("kid-1") == setup.key.jwk
