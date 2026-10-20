from collections.abc import Callable
from datetime import datetime, timedelta

from app.intent.application.commands.create_payment_intent_command import (
    CreatePaymentIntentCommand,
)
from app.intent.application.dtos.create_payment_intent_result import CreatePaymentIntentResult
from app.intent.application.dtos.payment_intent_view import PaymentIntentView
from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.exceptions.amount_exceeds_limit_error import AmountExceedsLimitError
from app.intent.domain.exceptions.idempotency_key_reused_error import IdempotencyKeyReusedError
from app.intent.domain.exceptions.idempotency_race_error import IdempotencyRaceError
from app.intent.domain.interfaces.payment_intent_repository import PaymentIntentRepository
from app.intent.domain.value_objects.amount import Amount
from app.intent.domain.value_objects.request_fingerprint import RequestFingerprint


class CreatePaymentIntentUseCase:
    """Crée une intention (requires_confirmation), de façon idempotente par appelant et clé."""

    def __init__(
        self,
        repository: PaymentIntentRepository,
        clock: Callable[[], datetime],
        ttl: timedelta,
        max_amount_cents: int,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._ttl = ttl
        self._max_amount_cents = max_amount_cents

    def execute(self, command: CreatePaymentIntentCommand) -> CreatePaymentIntentResult:
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
        except IdempotencyRaceError:
            return self._replay_after_race(command, fingerprint)
        return CreatePaymentIntentResult(PaymentIntentView.from_entity(intent), created=True)

    def _replay_after_race(
        self, command: CreatePaymentIntentCommand, fingerprint: str
    ) -> CreatePaymentIntentResult:
        existing = self._repository.find_by_idempotency(command.caller, command.idempotency_key)
        if existing is None:
            raise IdempotencyRaceError
        return self._replay(existing, fingerprint)

    @staticmethod
    def _replay(
        existing: tuple[IdempotencyRecord, PaymentIntent], fingerprint: str
    ) -> CreatePaymentIntentResult:
        record, intent = existing
        if record.request_hash != fingerprint:
            raise IdempotencyKeyReusedError
        return CreatePaymentIntentResult(PaymentIntentView.from_entity(intent), created=False)
