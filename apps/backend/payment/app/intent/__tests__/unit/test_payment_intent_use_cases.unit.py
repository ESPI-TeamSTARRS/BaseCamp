from datetime import UTC, datetime, timedelta

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.intent.__tests__.support import LIMIT, InMemoryRepository, make_command
from app.intent.application.create_payment_intent import CreatePaymentIntentUseCase
from app.intent.application.get_payment_intent import GetPaymentIntentUseCase
from app.intent.application.get_payment_intent_by_order import GetPaymentIntentByOrderUseCase
from app.intent.domain.exceptions.amount_exceeds_limit_error import AmountExceedsLimitError
from app.intent.domain.exceptions.duplicate_order_reference_error import (
    DuplicateOrderReferenceError,
)
from app.intent.domain.exceptions.idempotency_key_reused_error import IdempotencyKeyReusedError
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def _create_use_case(repo: InMemoryRepository) -> CreatePaymentIntentUseCase:
    return CreatePaymentIntentUseCase(
        repo, lambda: NOW, timedelta(minutes=30), LIMIT, InMemoryBusinessEventLogger()
    )


class TestCreatePaymentIntent:
    def test_creates_an_intent_requiring_confirmation(self) -> None:
        result = _create_use_case(InMemoryRepository()).execute(make_command())

        assert result.created is True
        assert result.intent.status == "requires_confirmation"
        assert result.intent.amount == 2500
        assert result.intent.expires_at == NOW + timedelta(minutes=30)

    def test_replaying_the_same_request_returns_the_same_intent(self) -> None:
        use_case = _create_use_case(InMemoryRepository())
        first = use_case.execute(make_command())

        second = use_case.execute(make_command())

        assert second.created is False
        assert second.intent.id == first.intent.id

    def test_same_key_with_a_different_body_is_refused(self) -> None:
        use_case = _create_use_case(InMemoryRepository())
        use_case.execute(make_command())

        with pytest.raises(IdempotencyKeyReusedError):
            use_case.execute(make_command(amount=9999))

    def test_second_intent_for_the_same_order_is_refused(self) -> None:
        use_case = _create_use_case(InMemoryRepository())
        use_case.execute(make_command())

        with pytest.raises(DuplicateOrderReferenceError):
            use_case.execute(make_command(idempotency_key="key-0002"))

    def test_keys_are_scoped_per_caller(self) -> None:
        use_case = _create_use_case(InMemoryRepository())
        use_case.execute(make_command())

        with pytest.raises(DuplicateOrderReferenceError):
            use_case.execute(make_command(caller="other"))

    def test_amount_above_the_limit_is_refused(self) -> None:
        with pytest.raises(AmountExceedsLimitError):
            _create_use_case(InMemoryRepository()).execute(make_command(amount=LIMIT + 1))

    def test_amount_equal_to_the_limit_is_accepted(self) -> None:
        assert _create_use_case(InMemoryRepository()).execute(make_command(amount=LIMIT)).created


class TestGetPaymentIntent:
    def test_returns_the_intent_by_id(self) -> None:
        repo = InMemoryRepository()
        created = _create_use_case(repo).execute(make_command()).intent

        found = GetPaymentIntentUseCase(repo, InMemoryBusinessEventLogger()).execute(
            str(created.id)
        )

        assert found == created
        assert found.refunded_amount == 0

    @pytest.mark.parametrize("intent_id", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
    def test_unknown_or_malformed_id_is_not_found(self, intent_id: str) -> None:
        with pytest.raises(PaymentIntentNotFoundError):
            GetPaymentIntentUseCase(InMemoryRepository(), InMemoryBusinessEventLogger()).execute(
                intent_id
            )

    def test_returns_the_intent_by_order_reference(self) -> None:
        repo = InMemoryRepository()
        created = _create_use_case(repo).execute(make_command()).intent

        assert (
            GetPaymentIntentByOrderUseCase(repo, InMemoryBusinessEventLogger()).execute("CMD-1")
            == created
        )

    def test_unknown_order_reference_is_not_found(self) -> None:
        with pytest.raises(PaymentIntentNotFoundError):
            GetPaymentIntentByOrderUseCase(
                InMemoryRepository(), InMemoryBusinessEventLogger()
            ).execute("CMD-404")


class _LosingTheRaceRepository(InMemoryRepository):
    """Une autre instance enregistre la même demande entre la lecture et l'écriture."""

    def __init__(self) -> None:
        super().__init__()
        self.armed = True

    def find_by_idempotency(self, caller: str, key: str):  # type: ignore[no-untyped-def]
        found = super().find_by_idempotency(caller, key)
        if self.armed and found is None:
            self.armed = False
            # le gagnant s'insère juste après notre lecture à vide
            _create_use_case(self).execute(make_command())
            return None
        return found


class TestConcurrentCreationAcrossInstances:
    def test_losing_the_race_on_the_order_reference_replays_the_winner_instead_of_a_409(
        self,
    ) -> None:
        repo = _LosingTheRaceRepository()

        result = _create_use_case(repo).execute(make_command())

        assert result.created is False
        assert len(repo.intents) == 1
        assert result.intent.id == str(next(iter(repo.intents)))

    def test_a_real_duplicate_order_with_another_key_is_still_a_conflict(self) -> None:
        repo = InMemoryRepository()
        _create_use_case(repo).execute(make_command())

        with pytest.raises(DuplicateOrderReferenceError):
            _create_use_case(repo).execute(make_command(idempotency_key="key-0002"))
