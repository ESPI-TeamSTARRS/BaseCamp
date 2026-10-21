from uuid import uuid4

from app.intent.domain.value_objects.amount import Amount
from app.refund.domain.value_objects.refund_fingerprint import RefundFingerprint


class TestRefundFingerprint:
    def test_the_same_request_gives_the_same_fingerprint(self) -> None:
        intent_id = uuid4()

        assert RefundFingerprint.of(intent_id, Amount(4000)) == RefundFingerprint.of(
            intent_id, Amount(4000)
        )

    def test_another_amount_or_another_intent_gives_another_fingerprint(self) -> None:
        intent_id = uuid4()
        reference = RefundFingerprint.of(intent_id, Amount(4000))

        assert RefundFingerprint.of(intent_id, Amount(4001)) != reference
        assert RefundFingerprint.of(uuid4(), Amount(4000)) != reference

    def test_the_fingerprint_is_a_sha256_hex_digest(self) -> None:
        assert len(RefundFingerprint.of(uuid4(), Amount(1))) == 64
