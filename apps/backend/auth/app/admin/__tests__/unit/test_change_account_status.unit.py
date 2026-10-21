from uuid import uuid4

import pytest

from app.admin.__tests__.fakes import AdminStore, FakeAdminUnitOfWork, FakeClock, account
from app.admin.application.change_account_status import ChangeAccountStatusUseCase
from app.admin.domain.exceptions.admin_errors import (
    AccountNotFoundError,
    CannotDisableLastOperatorError,
    CannotDisableSelfError,
)
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger


class Setup:
    def __init__(self, *accounts) -> None:  # type: ignore[no-untyped-def]
        self.store = AdminStore(*accounts)
        self.events = InMemoryBusinessEventLogger()
        self.use_case = ChangeAccountStatusUseCase(
            lambda: FakeAdminUnitOfWork(self.store), FakeClock(), self.events
        )


class TestLastOperatorRule:
    def test_the_sole_active_operator_cannot_be_disabled_even_by_a_stale_caller(self) -> None:
        sole = account("ops@example.com", "operator")
        setup = Setup(sole, account("client@example.com"))

        with pytest.raises(CannotDisableLastOperatorError):
            setup.use_case.disable(uuid4(), sole.id)  # appelant dont le compte a ete retire

        assert not setup.store.accounts[sole.id].disabled
        [event] = setup.events.events
        assert (event.event, event.reason) == (
            "auth.admin_action_refused",
            "cannot_disable_last_operator",
        )

    def test_a_disabled_operator_is_not_counted_as_active(self) -> None:
        active = account("a@example.com", "operator")
        gone = account("b@example.com", "operator", disabled=True)
        setup = Setup(active, gone)

        with pytest.raises(CannotDisableLastOperatorError):
            setup.use_case.disable(uuid4(), active.id)

    def test_one_of_two_operators_can_be_disabled(self) -> None:
        first = account("a@example.com", "operator")
        second = account("b@example.com", "operator")
        setup = Setup(first, second)

        result = setup.use_case.disable(first.id, second.id)

        assert result.disabled is True
        assert setup.store.accounts[second.id].disabled

    def test_a_customer_can_always_be_disabled(self) -> None:
        operator = account("ops@example.com", "operator")
        client = account("client@example.com")
        setup = Setup(operator, client)

        setup.use_case.disable(operator.id, client.id)

        assert setup.store.accounts[client.id].disabled


class TestRules:
    def test_self_disable_is_refused_before_anything_else(self) -> None:
        first = account("a@example.com", "operator")
        second = account("b@example.com", "operator")
        setup = Setup(first, second)

        with pytest.raises(CannotDisableSelfError):
            setup.use_case.disable(first.id, first.id)

        assert setup.store.commits == 0

    def test_disabling_reports_and_revokes_the_sessions(self) -> None:
        operator = account("ops@example.com", "operator")
        client = account("client@example.com")
        setup = Setup(operator, client)
        setup.store.sessions[client.id] = 3

        setup.use_case.disable(operator.id, client.id, "203.0.113.7")

        [event] = setup.events.events
        assert dict(event.attributes) == {"sessions_revoked": 3, "already_disabled": False}
        assert event.client_ip == "203.0.113.7"
        assert setup.store.sessions == {}

    def test_disabling_twice_is_idempotent_and_revokes_nothing_the_second_time(self) -> None:
        operator = account("ops@example.com", "operator")
        client = account("client@example.com")
        setup = Setup(operator, client)
        setup.store.sessions[client.id] = 1
        setup.use_case.disable(operator.id, client.id)
        setup.store.sessions[client.id] = 1  # un jeton qui aurait survecu

        setup.use_case.disable(operator.id, client.id)

        assert dict(setup.events.events[-1].attributes)["already_disabled"] is True

    def test_unknown_accounts_are_refused_and_logged(self) -> None:
        operator = account("ops@example.com", "operator")
        setup = Setup(operator)

        for action in (setup.use_case.disable, setup.use_case.enable):
            with pytest.raises(AccountNotFoundError):
                action(operator.id, uuid4())

        assert [e.reason for e in setup.events.events] == ["account_not_found"] * 2

    def test_enabling_an_enabled_account_is_a_harmless_repeat(self) -> None:
        operator = account("ops@example.com", "operator")
        client = account("client@example.com")
        setup = Setup(operator, client)

        setup.use_case.enable(operator.id, client.id)

        assert dict(setup.events.events[0].attributes) == {"already_enabled": True}
