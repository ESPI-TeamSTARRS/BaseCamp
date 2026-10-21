import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.login.__tests__.fakes import (
    ACCOUNT_SECRET,
    EMAIL,
    FakeAccessTokenSigner,
    FakeClock,
    FakeEmailFingerprinter,
    FakePasswordVerifier,
    FakeRefreshTokenGenerator,
    FakeStore,
    FakeUnitOfWork,
    make_account,
)
from app.login.application.invalid_credentials_error import InvalidCredentialsError
from app.login.application.login_account import LoginAccountUseCase
from app.login.domain.entities.account import Account

ACCESS_TTL = 900
REFRESH_TTL = 604800


class Setup:
    def __init__(self, *accounts: Account, outdated: bool = False) -> None:
        self.store = FakeStore(*accounts)
        self.verifier = FakePasswordVerifier(outdated=outdated)
        self.signer = FakeAccessTokenSigner()
        self.clock = FakeClock()
        self.events = InMemoryBusinessEventLogger()
        self.use_case = LoginAccountUseCase(
            lambda: FakeUnitOfWork(self.store),
            self.verifier,
            self.signer,
            FakeRefreshTokenGenerator(),
            self.clock,
            self.events,
            FakeEmailFingerprinter(),
            ACCESS_TTL,
            REFRESH_TTL,
        )


class TestSuccessfulLogin:
    def test_returns_an_access_token_and_a_refresh_token(self) -> None:
        account = make_account()
        setup = Setup(account)

        result = setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        assert result.access_token == f"signed::{account.id}"
        assert result.expires_in == ACCESS_TTL
        assert result.refresh_token == "raw-refresh-token"
        assert result.refresh_expires_in == REFRESH_TTL

    def test_access_token_claims_describe_the_account_for_15_minutes(self) -> None:
        account = make_account(role="operator", verified=False)
        setup = Setup(account)

        setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        claims = setup.signer.signed[0]
        assert claims.subject == account.id
        assert claims.roles == ("operator",)
        assert claims.email_verified is False
        assert (claims.expires_at - claims.issued_at).total_seconds() == ACCESS_TTL
        assert claims.token_id

    def test_each_token_gets_its_own_identifier(self) -> None:
        setup = Setup(make_account())

        setup.use_case.execute(EMAIL, ACCOUNT_SECRET)
        setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        assert setup.signer.signed[0].token_id != setup.signer.signed[1].token_id

    def test_only_the_hash_of_the_refresh_token_is_stored(self) -> None:
        account = make_account()
        setup = Setup(account)

        setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        (stored,) = setup.store.refresh_tokens
        assert stored.user_id == account.id
        assert stored.token_hash == FakeRefreshTokenGenerator().digest("raw-refresh-token")
        assert "raw-refresh-token" not in repr(stored)
        assert (stored.expires_at - stored.created_at).total_seconds() == REFRESH_TTL

    def test_the_email_is_normalized(self) -> None:
        setup = Setup(make_account())

        result = setup.use_case.execute("  Camille@Example.COM \n", ACCOUNT_SECRET)

        assert result.access_token

    def test_an_unverified_account_can_log_in(self) -> None:
        setup = Setup(make_account(verified=False))

        assert setup.use_case.execute(EMAIL, ACCOUNT_SECRET).access_token

    def test_success_emits_login_succeeded_without_sensitive_data(self) -> None:
        account = make_account()
        setup = Setup(account)

        setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        (event,) = setup.events.events
        assert (event.event, event.outcome, event.reason) == (
            "auth.login_succeeded",
            Outcome.SUCCESS,
            None,
        )
        assert (event.resource_type, event.resource_id) == ("account", str(account.id))
        assert (event.actor_type, event.actor_id) == ("user", str(account.id))
        assert event.attributes["email_hash"] == FakeEmailFingerprinter().fingerprint(EMAIL)
        assert event.attributes["hash_upgraded"] is False
        assert EMAIL not in repr(event)
        assert ACCOUNT_SECRET not in repr(event)
        assert "raw-refresh-token" not in repr(event)


class TestRejectedLogin:
    @pytest.mark.parametrize(
        ("account", "email", "password", "cause"),
        [
            (make_account(), EMAIL, "mauvais-mot-de-passe", "wrong_password"),
            (make_account(), "inconnu@example.com", ACCOUNT_SECRET, "unknown_account"),
            (make_account(disabled=True), EMAIL, ACCOUNT_SECRET, "account_disabled"),
        ],
    )
    def test_every_cause_raises_the_same_error_and_issues_nothing(
        self, account: Account, email: str, password: str, cause: str
    ) -> None:
        setup = Setup(account)

        with pytest.raises(InvalidCredentialsError) as raised:
            setup.use_case.execute(email, password, "203.0.113.7")

        assert raised.value.message == "Identifiants invalides."
        assert setup.signer.signed == []
        assert setup.store.refresh_tokens == []
        (event,) = setup.events.events
        assert (event.event, event.outcome, event.reason) == (
            "auth.login_failed",
            Outcome.DENIED,
            "invalid_credentials",
        )
        assert event.attributes["cause"] == cause
        assert event.client_ip == "203.0.113.7"
        assert email not in repr(event)
        assert password not in repr(event)

    def test_a_known_account_is_referenced_by_the_event_an_unknown_one_is_not(self) -> None:
        account = make_account()
        setup = Setup(account)

        with pytest.raises(InvalidCredentialsError):
            setup.use_case.execute(EMAIL, "mauvais-mot-de-passe")
        with pytest.raises(InvalidCredentialsError):
            setup.use_case.execute("inconnu@example.com", ACCOUNT_SECRET)

        known, unknown = setup.events.events
        assert known.resource_id == str(account.id)
        assert (unknown.resource_type, unknown.resource_id) == ("account", None)

    def test_an_unknown_email_costs_one_decoy_verification(self) -> None:
        setup = Setup(make_account())

        with pytest.raises(InvalidCredentialsError):
            setup.use_case.execute("inconnu@example.com", ACCOUNT_SECRET)

        assert (setup.verifier.decoys, setup.verifier.verifications) == (1, 0)

    @pytest.mark.parametrize("disabled", [False, True])
    def test_a_known_account_costs_exactly_one_real_verification(self, disabled: bool) -> None:
        setup = Setup(make_account(disabled=disabled))

        with pytest.raises(InvalidCredentialsError):
            setup.use_case.execute(EMAIL, "mauvais-mot-de-passe")

        assert (setup.verifier.decoys, setup.verifier.verifications) == (0, 1)

    def test_a_disabled_account_is_checked_with_the_right_password_too(self) -> None:
        setup = Setup(make_account(disabled=True))

        with pytest.raises(InvalidCredentialsError):
            setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        assert setup.verifier.verifications == 1


class TestPasswordRehash:
    def test_a_hash_made_with_old_parameters_is_replaced_after_a_successful_login(self) -> None:
        account = make_account()
        setup = Setup(account, outdated=True)

        setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        assert setup.verifier.hashed == [ACCOUNT_SECRET]
        assert setup.store.accounts[account.id].password_hash.startswith("rehashed::")
        assert setup.events.events[0].attributes["hash_upgraded"] is True

    def test_an_up_to_date_hash_is_left_alone(self) -> None:
        account = make_account()
        setup = Setup(account)

        setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        assert setup.verifier.hashed == []
        assert setup.store.accounts[account.id].password_hash == account.password_hash

    def test_a_failed_login_never_rehashes(self) -> None:
        account = make_account()
        setup = Setup(account, outdated=True)

        with pytest.raises(InvalidCredentialsError):
            setup.use_case.execute(EMAIL, "mauvais-mot-de-passe")

        assert setup.verifier.hashed == []
