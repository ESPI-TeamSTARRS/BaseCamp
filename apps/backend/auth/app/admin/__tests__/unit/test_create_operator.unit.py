import pytest

from app.admin.__tests__.fakes import AdminStore, FakeAdminUnitOfWork, FakeClock, FakeHasher
from app.admin.application.create_operator import CreateOperatorUseCase
from app.admin.domain.exceptions.admin_errors import OperatorAlreadyExistsError
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.registration.domain.exceptions.invalid_email_error import InvalidEmailError
from app.registration.domain.exceptions.weak_password_error import WeakPasswordError
from app.registration.domain.interfaces.common_password_list import CommonPasswordList
from app.registration.domain.services.password_policy import PasswordPolicy

STRONG = "Bivouac-au-sommet-2026"
TOO_COMMON = "aaaa-aaaa-aaaa"


class NoCommon(CommonPasswordList):
    def contains(self, password: str) -> bool:
        return password == TOO_COMMON


class Setup:
    def __init__(self) -> None:
        self.store = AdminStore()
        self.events = InMemoryBusinessEventLogger()
        self.use_case = CreateOperatorUseCase(
            lambda: FakeAdminUnitOfWork(self.store),
            PasswordPolicy(NoCommon()),
            FakeHasher(),
            FakeClock(),
            self.events,
        )


class TestCreateOperator:
    def test_it_creates_a_verified_operator_with_a_hashed_password(self) -> None:
        setup = Setup()

        account_id = setup.use_case.execute("  Ops@Example.COM ", STRONG)

        [stored] = setup.store.accounts.values()
        assert (str(stored.id), stored.email, stored.role) == (
            account_id,
            "ops@example.com",
            "operator",
        )
        assert stored.email_verified is True
        assert setup.store.password_hashes[stored.id] == FakeHasher().hash(STRONG)

    def test_it_logs_the_creation_without_address_or_password(self) -> None:
        setup = Setup()

        setup.use_case.execute("ops@example.com", STRONG)

        [event] = setup.events.events
        assert (event.event, event.outcome, event.actor_type) == (
            "auth.operator_created",
            Outcome.SUCCESS,
            "cli",
        )
        assert "ops@example.com" not in repr(event)
        assert STRONG not in repr(event)

    @pytest.mark.parametrize("password", ["court", TOO_COMMON])
    def test_a_weak_password_is_refused_and_logged_with_its_rule(self, password: str) -> None:
        setup = Setup()

        with pytest.raises(WeakPasswordError):
            setup.use_case.execute("ops@example.com", password)

        assert setup.store.accounts == {}
        [event] = setup.events.events
        assert (event.outcome, event.reason) == (Outcome.DENIED, "weak_password")
        assert password not in repr(event)

    def test_an_invalid_address_is_refused(self) -> None:
        with pytest.raises(InvalidEmailError):
            Setup().use_case.execute("pas-une-adresse", STRONG)

    def test_an_existing_address_is_refused_without_changing_it(self) -> None:
        setup = Setup()
        setup.use_case.execute("ops@example.com", STRONG)
        setup.events.events.clear()

        with pytest.raises(OperatorAlreadyExistsError):
            setup.use_case.execute("ops@example.com", STRONG)

        assert len(setup.store.accounts) == 1
        assert setup.events.events[0].reason == "operator_exists"
