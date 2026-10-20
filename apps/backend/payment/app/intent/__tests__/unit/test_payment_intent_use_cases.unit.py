from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.intent.application.commands.create_payment_intent_command import (
    CreatePaymentIntentCommand,
)
from app.intent.application.create_payment_intent import CreatePaymentIntentUseCase
from app.intent.application.get_payment_intent import GetPaymentIntentUseCase
from app.intent.application.get_payment_intent_by_order import GetPaymentIntentByOrderUseCase
from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.exceptions.amount_exceeds_limit_error import AmountExceedsLimitError
from app.intent.domain.exceptions.duplicate_order_reference_error import (
    DuplicateOrderReferenceError,
)
from app.intent.domain.exceptions.idempotency_key_reused_error import IdempotencyKeyReusedError
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.intent.domain.interfaces.payment_intent_repository import PaymentIntentRepository

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
LIMIT = 500_000


class InMemoryRepository(PaymentIntentRepository):
    def __init__(self) -> None:
        self.intents: dict[UUID, PaymentIntent] = {}
        self.records: dict[tuple[str, str], IdempotencyRecord] = {}

    def add(self, intent: PaymentIntent, record: IdempotencyRecord) -> None:
        if any(i.order_reference == intent.order_reference for i in self.intents.values()):
            raise DuplicateOrderReferenceError
        self.intents[intent.id] = intent
        self.records[(record.caller, record.key)] = record

    def find_by_idempotency(
        self, caller: str, key: str
    ) -> tuple[IdempotencyRecord, PaymentIntent] | None:
        record = self.records.get((caller, key))
        return (record, self.intents[record.intent_id]) if record else None

    def get_by_id(self, intent_id: UUID) -> PaymentIntent | None:
        return self.intents.get(intent_id)

    def get_by_order_reference(self, order_reference: str) -> PaymentIntent | None:
        return next(
            (i for i in self.intents.values() if i.order_reference == order_reference), None
        )


def _command(**overrides: object) -> CreatePaymentIntentCommand:
    values: dict[str, object] = {
        "caller": "shop",
        "idempotency_key": "key-0001",
        "order_reference": "CMD-1",
        "amount": 2500,
        "currency": "EUR",
    }
    values.update(overrides)
    return CreatePaymentIntentCommand(**values)  # type: ignore[arg-type]


def _create_use_case(repo: InMemoryRepository) -> CreatePaymentIntentUseCase:
    return CreatePaymentIntentUseCase(repo, lambda: NOW, timedelta(minutes=30), LIMIT)


class TestCreatePaymentIntent:
    def test_creates_an_intent_requiring_confirmation(self) -> None:
        result = _create_use_case(InMemoryRepository()).execute(_command())

        assert result.created is True
        assert result.intent.status == "requires_confirmation"
        assert result.intent.amount == 2500
        assert result.intent.expires_at == NOW + timedelta(minutes=30)

    def test_replaying_the_same_request_returns_the_same_intent(self) -> None:
        use_case = _create_use_case(InMemoryRepository())
        first = use_case.execute(_command())

        second = use_case.execute(_command())

        assert second.created is False
        assert second.intent.id == first.intent.id

    def test_same_key_with_a_different_body_is_refused(self) -> None:
        use_case = _create_use_case(InMemoryRepository())
        use_case.execute(_command())

        with pytest.raises(IdempotencyKeyReusedError):
            use_case.execute(_command(amount=9999))

    def test_second_intent_for_the_same_order_is_refused(self) -> None:
        use_case = _create_use_case(InMemoryRepository())
        use_case.execute(_command())

        with pytest.raises(DuplicateOrderReferenceError):
            use_case.execute(_command(idempotency_key="key-0002"))

    def test_keys_are_scoped_per_caller(self) -> None:
        use_case = _create_use_case(InMemoryRepository())
        use_case.execute(_command())

        with pytest.raises(DuplicateOrderReferenceError):
            use_case.execute(_command(caller="other"))

    def test_amount_above_the_limit_is_refused(self) -> None:
        with pytest.raises(AmountExceedsLimitError):
            _create_use_case(InMemoryRepository()).execute(_command(amount=LIMIT + 1))

    def test_amount_equal_to_the_limit_is_accepted(self) -> None:
        assert _create_use_case(InMemoryRepository()).execute(_command(amount=LIMIT)).created


class TestGetPaymentIntent:
    def test_returns_the_intent_by_id(self) -> None:
        repo = InMemoryRepository()
        created = _create_use_case(repo).execute(_command()).intent

        found = GetPaymentIntentUseCase(repo).execute(str(created.id))

        assert found == created
        assert found.refunded_amount == 0

    @pytest.mark.parametrize("intent_id", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
    def test_unknown_or_malformed_id_is_not_found(self, intent_id: str) -> None:
        with pytest.raises(PaymentIntentNotFoundError):
            GetPaymentIntentUseCase(InMemoryRepository()).execute(intent_id)

    def test_returns_the_intent_by_order_reference(self) -> None:
        repo = InMemoryRepository()
        created = _create_use_case(repo).execute(_command()).intent

        assert GetPaymentIntentByOrderUseCase(repo).execute("CMD-1") == created

    def test_unknown_order_reference_is_not_found(self) -> None:
        with pytest.raises(PaymentIntentNotFoundError):
            GetPaymentIntentByOrderUseCase(InMemoryRepository()).execute("CMD-404")
