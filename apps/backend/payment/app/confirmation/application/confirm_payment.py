from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from app.confirmation.application.commands.confirm_payment_command import ConfirmPaymentCommand
from app.confirmation.domain.entities.confirmation_record import ConfirmationRecord
from app.confirmation.domain.enums.payment_method import PaymentMethod
from app.confirmation.domain.enums.provider_outcome import ProviderOutcome
from app.confirmation.domain.exceptions.confirmation_key_reused_error import (
    ConfirmationKeyReusedError,
)
from app.confirmation.domain.exceptions.intent_not_confirmable_error import (
    IntentNotConfirmableError,
)
from app.confirmation.domain.interfaces.confirmation_unit_of_work import ConfirmationUnitOfWork
from app.confirmation.domain.interfaces.payment_provider import PaymentProvider
from app.confirmation.domain.value_objects.confirmation_fingerprint import ConfirmationFingerprint
from app.intent.application.dtos.payment_intent_view import PaymentIntentView
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction


class ConfirmPaymentUseCase:
    """Confirme une intention : une seule fois, de façon idempotente, état et grand livre ensemble.

    Le montant vient toujours de l'intention stockée, jamais de la demande. L'intention est
    verrouillée (ligne) pendant tout le traitement : deux confirmations concurrentes se suivent.
    """

    def __init__(
        self,
        unit_of_work: ConfirmationUnitOfWork,
        provider: PaymentProvider,
        clock: Callable[[], datetime],
    ) -> None:
        self._unit_of_work = unit_of_work
        self._provider = provider
        self._clock = clock

    def execute(self, command: ConfirmPaymentCommand) -> PaymentIntentView:
        intent_id = self._parse(command.intent_id)
        method = PaymentMethod(command.payment_method)
        fingerprint = ConfirmationFingerprint.of(intent_id, method)
        with self._unit_of_work.begin() as session:
            intent = session.lock_intent(intent_id)
            if intent is None:
                raise PaymentIntentNotFoundError
            existing = session.find_record(command.caller, command.idempotency_key)
            if existing:
                return self._replay(existing, intent, fingerprint)
            now = self._clock()
            if not intent.can_be_confirmed(now):
                raise IntentNotConfirmableError
            settled, ledger = self._settle(intent, method, now)
            record = ConfirmationRecord(
                command.caller, command.idempotency_key, fingerprint, intent.id
            )
            session.save(settled, record, ledger)
        return PaymentIntentView.from_entity(settled)

    @staticmethod
    def _parse(intent_id: str) -> UUID:
        try:
            return UUID(intent_id)
        except ValueError:
            raise PaymentIntentNotFoundError from None

    def _settle(
        self, intent: PaymentIntent, method: PaymentMethod, now: datetime
    ) -> tuple[PaymentIntent, LedgerTransaction | None]:
        outcome = self._provider.authorize(method, intent.amount)
        if outcome is ProviderOutcome.APPROVED:
            return intent.succeed(), LedgerTransaction.payment_received(
                intent.id, intent.amount, now
            )
        return intent.fail(), None

    @staticmethod
    def _replay(
        record: ConfirmationRecord, intent: PaymentIntent, fingerprint: str
    ) -> PaymentIntentView:
        if record.request_hash != fingerprint:
            raise ConfirmationKeyReusedError
        return PaymentIntentView.from_entity(intent)
