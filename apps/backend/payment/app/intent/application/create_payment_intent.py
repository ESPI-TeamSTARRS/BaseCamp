from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.intent.application.commands.create_payment_intent_command import (
    CreatePaymentIntentCommand,
)
from app.intent.application.dtos.create_payment_intent_result import CreatePaymentIntentResult
from app.intent.application.dtos.payment_intent_view import PaymentIntentView
from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.exceptions.amount_exceeds_limit_error import AmountExceedsLimitError
from app.intent.domain.exceptions.duplicate_order_reference_error import (
    DuplicateOrderReferenceError,
)
from app.intent.domain.exceptions.idempotency_key_reused_error import IdempotencyKeyReusedError
from app.intent.domain.exceptions.idempotency_race_error import IdempotencyRaceError
from app.intent.domain.interfaces.payment_intent_repository import PaymentIntentRepository
from app.intent.domain.value_objects.amount import Amount
from app.intent.domain.value_objects.request_fingerprint import RequestFingerprint

_REASON_BY_ERROR: dict[type[Exception], str] = {
    AmountExceedsLimitError: "amount_exceeds_limit",
    IdempotencyKeyReusedError: "idempotency_key_reused",
    DuplicateOrderReferenceError: "duplicate_order_reference",
}


class CreatePaymentIntentUseCase:
    """Crée une intention (requires_confirmation), de façon idempotente par appelant et clé."""

    def __init__(
        self,
        repository: PaymentIntentRepository,
        clock: Callable[[], datetime],
        ttl: timedelta,
        max_amount_cents: int,
        events: BusinessEventLogger,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._ttl = ttl
        self._max_amount_cents = max_amount_cents
        self._events = events

    def execute(self, command: CreatePaymentIntentCommand) -> CreatePaymentIntentResult:
        try:
            result = self._create(command)
        except tuple(_REASON_BY_ERROR) as error:
            self._events.log(
                BusinessEvent.denied(
                    "payment.intent_rejected",
                    _REASON_BY_ERROR[type(error)],
                    actor_type="service",
                    actor_id=command.caller,
                )
            )
            raise
        self._events.log(self._success_event(command, result))
        return result

    @staticmethod
    def _success_event(
        command: CreatePaymentIntentCommand, result: CreatePaymentIntentResult
    ) -> BusinessEvent:
        return BusinessEvent.success(
            "payment.intent_created" if result.created else "payment.intent_replayed",
            resource_type="payment_intent",
            resource_id=str(result.intent.id),
            actor_type="service",
            actor_id=command.caller,
            attributes={"amount_cents": result.intent.amount, "currency": result.intent.currency},
        )

    def _create(self, command: CreatePaymentIntentCommand) -> CreatePaymentIntentResult:
        if command.amount > self._max_amount_cents:
            raise AmountExceedsLimitError
        currency = Currency(command.currency)
        fingerprint = RequestFingerprint.of(command.order_reference, command.amount, currency)
        existing = self._repository.find_by_idempotency(command.caller, command.idempotency_key)
        if existing:
            return self._replay(existing, fingerprint)
        intent = PaymentIntent.create(
            command.order_reference, Amount(command.amount), currency, self._clock(), self._ttl
        )
        record = IdempotencyRecord(command.caller, command.idempotency_key, fingerprint, intent.id)
        try:
            self._repository.add(intent, record)
        except (IdempotencyRaceError, DuplicateOrderReferenceError) as error:
            # Une autre instance a enregistré la même demande entre notre lecture et notre écriture :
            # si c'est la même clé, on rejoue son résultat (200) ; sinon le conflit est réel.
            return self._replay_after_race(command, fingerprint, error)
        return CreatePaymentIntentResult(PaymentIntentView.from_entity(intent), created=True)

    def _replay_after_race(
        self, command: CreatePaymentIntentCommand, fingerprint: str, error: Exception
    ) -> CreatePaymentIntentResult:
        existing = self._repository.find_by_idempotency(command.caller, command.idempotency_key)
        if existing is None:
            raise error
        return self._replay(existing, fingerprint)

    @staticmethod
    def _replay(
        existing: tuple[IdempotencyRecord, PaymentIntent], fingerprint: str
    ) -> CreatePaymentIntentResult:
        record, intent = existing
        if record.request_hash != fingerprint:
            raise IdempotencyKeyReusedError
        return CreatePaymentIntentResult(PaymentIntentView.from_entity(intent), created=False)
