from uuid import uuid4

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.login.__tests__.fakes import (
    FakeAccessTokenVerifier,
    FakeClock,
    FakeStore,
    FakeUnitOfWork,
    make_account,
)
from app.login.application.get_current_account import GetCurrentAccountUseCase
from app.login.application.unauthenticated_error import UnauthenticatedError
from app.login.domain.entities.account import Account
from app.login.domain.enums.token_rejection import TokenRejection


def build(
    account: Account | None, reject: TokenRejection | None = None
) -> tuple[GetCurrentAccountUseCase, InMemoryBusinessEventLogger]:
    store = FakeStore(*([account] if account else []))
    events = InMemoryBusinessEventLogger()
    use_case = GetCurrentAccountUseCase(
        lambda: FakeUnitOfWork(store), FakeAccessTokenVerifier(reject), FakeClock(), events
    )
    return use_case, events


class TestGetCurrentAccount:
    def test_a_valid_token_returns_the_profile_without_the_password_hash(self) -> None:
        account = make_account(role="operator", verified=False)
        use_case, events = build(account)

        profile = use_case.execute(f"signed::{account.id}")

        assert profile.id == account.id
        assert profile.email == account.email
        assert profile.roles == ("operator",)
        assert profile.email_verified is False
        assert "password" not in vars(profile)
        assert events.events == []

    @pytest.mark.parametrize(
        "rejection", [TokenRejection.EXPIRED, TokenRejection.INVALID], ids=lambda r: r.value
    )
    def test_a_rejected_token_raises_and_logs_the_internal_reason(
        self, rejection: TokenRejection
    ) -> None:
        use_case, events = build(make_account(), reject=rejection)

        with pytest.raises(UnauthenticatedError) as raised:
            use_case.execute("n-importe-quoi")

        assert raised.value.message == "Authentification requise."
        (event,) = events.events
        assert (event.event, event.outcome, event.reason) == (
            "auth.token_rejected",
            Outcome.DENIED,
            rejection.value,
        )
        assert event.resource_type == "access_token"
        assert "n-importe-quoi" not in repr(event)

    def test_a_valid_token_of_an_unknown_account_is_revoked(self) -> None:
        use_case, events = build(None)

        with pytest.raises(UnauthenticatedError):
            use_case.execute(f"signed::{uuid4()}")

        assert events.events[0].reason == "revoked"

    def test_a_valid_token_of_a_disabled_account_is_revoked(self) -> None:
        account = make_account(disabled=True)
        use_case, events = build(account)

        with pytest.raises(UnauthenticatedError):
            use_case.execute(f"signed::{account.id}")

        assert events.events[0].reason == "revoked"
        assert events.events[0].actor_id == str(account.id)
