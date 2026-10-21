from uuid import uuid4

from app.confirmation.domain.enums.payment_method import PaymentMethod
from app.confirmation.domain.value_objects.confirmation_fingerprint import ConfirmationFingerprint


class TestConfirmationFingerprint:
    def test_is_stable_for_the_same_request(self) -> None:
        intent_id = uuid4()

        assert ConfirmationFingerprint.of(intent_id, PaymentMethod.SUCCESS) == (
            ConfirmationFingerprint.of(intent_id, PaymentMethod.SUCCESS)
        )

    def test_changes_with_the_payment_method(self) -> None:
        intent_id = uuid4()

        assert ConfirmationFingerprint.of(intent_id, PaymentMethod.SUCCESS) != (
            ConfirmationFingerprint.of(intent_id, PaymentMethod.DECLINED)
        )

    def test_changes_with_the_intent(self) -> None:
        assert ConfirmationFingerprint.of(uuid4(), PaymentMethod.SUCCESS) != (
            ConfirmationFingerprint.of(uuid4(), PaymentMethod.SUCCESS)
        )
