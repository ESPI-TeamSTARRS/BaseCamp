"""Signature du webhook de payment : vecteur du contrat (docs/services/payment.md), fenêtre de 5 min, rotation."""

import hashlib
import hmac

import pytest

from app.payment_confirmation.domain.errors.invalid_webhook_signature_error import (
    InvalidWebhookSignatureError,
)
from app.payment_confirmation.domain.services.webhook_signature_verifier import (
    WebhookSignatureVerifier,
)

PUBLISHED_EXAMPLE = (
    "whsec_exemple_0123456789abcdef01234567"  # exemple publié dans docs/services/payment.md
)
TIMESTAMP = 1790000000
BODY = (
    b'{"id":"0b6d4e0e-6a3f-4c58-9d8e-5f0f4d1d9a11","type":"payment.succeeded",'
    b'"created_at":"2026-10-21T09:00:00.123Z","data":{"payment_intent_id":'
    b'"7d2f3c1e-8a41-4d3b-9c55-2a6e0f9b1c42","order_reference":"CMD-2026-0001",'
    b'"amount":4990,"currency":"EUR","status":"succeeded"}}'
)
CONTRACT_HEADER = "t=1790000000,v1=21fa5b167eea0d087d55bd99aa776360368b23f1ff542077eaee49f7618acd9e"


def _sign(secret: str, body: bytes = BODY, timestamp: int = TIMESTAMP) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return digest.hexdigest()


def _verifier(
    secrets: tuple[str, ...] = (PUBLISHED_EXAMPLE,), now: float = TIMESTAMP, tolerance: int = 300
) -> WebhookSignatureVerifier:
    return WebhookSignatureVerifier(secrets, tolerance, lambda: now)


def _reason(verifier: WebhookSignatureVerifier, header: str | None, body: bytes = BODY) -> str:
    with pytest.raises(InvalidWebhookSignatureError) as error:
        verifier.verify(header, body)
    return error.value.reason


class TestAcceptedSignatures:
    def test_accepts_the_contract_test_vector(self) -> None:
        _verifier().verify(CONTRACT_HEADER, BODY)

    def test_accepts_any_v1_during_a_rotation(self) -> None:
        old = "whsec_ancien_secret_0123456789abcdef0123"
        header = f"t={TIMESTAMP},v1={_sign(old)},v1={_sign(PUBLISHED_EXAMPLE)}"

        _verifier((PUBLISHED_EXAMPLE,)).verify(header, BODY)
        _verifier((old, "whsec_autre_secret_0123456789abcdef01234")).verify(header, BODY)

    def test_accepts_the_edges_of_the_five_minute_window(self) -> None:
        _verifier(now=TIMESTAMP + 300).verify(CONTRACT_HEADER, BODY)
        _verifier(now=TIMESTAMP - 300).verify(CONTRACT_HEADER, BODY)


class TestRejectedSignatures:
    def test_rejects_a_timestamp_outside_the_window_even_when_the_signature_is_valid(self) -> None:
        assert _reason(_verifier(now=TIMESTAMP + 301), CONTRACT_HEADER) == "timestamp_out_of_window"
        assert _reason(_verifier(now=TIMESTAMP - 301), CONTRACT_HEADER) == "timestamp_out_of_window"

    def test_rejects_an_altered_body(self) -> None:
        altered = BODY.replace(b"4990", b"1")

        assert _reason(_verifier(), CONTRACT_HEADER, altered) == "signature_mismatch"

    def test_rejects_a_signature_made_with_another_secret(self) -> None:
        header = f"t={TIMESTAMP},v1={_sign('autre-secret-0123456789abcdef0123456789')}"

        assert _reason(_verifier(), header) == "signature_mismatch"

    def test_a_timestamp_swapped_into_the_header_breaks_the_signature(self) -> None:
        header = f"t={TIMESTAMP + 1},v1={_sign(PUBLISHED_EXAMPLE)}"

        assert _reason(_verifier(now=TIMESTAMP + 1), header) == "signature_mismatch"

    def test_rejects_a_missing_or_malformed_header(self) -> None:
        verifier = _verifier()

        assert _reason(verifier, None) == "signature_missing"
        assert _reason(verifier, "") == "signature_missing"
        assert _reason(verifier, "v1=abcd") == "signature_malformed"
        assert _reason(verifier, f"t=abc,v1={_sign(PUBLISHED_EXAMPLE)}") == "signature_malformed"
        assert _reason(verifier, f"t={TIMESTAMP}") == "signature_malformed"
        assert _reason(verifier, f"t={TIMESTAMP},v1=pas-de-l-hex") == "signature_mismatch"

    def test_rejects_everything_when_no_secret_is_configured(self) -> None:
        assert _reason(_verifier(()), CONTRACT_HEADER) == "webhook_not_configured"
        # Un secret vide ne doit jamais valider une signature calculée avec une clé vide.
        forged = f"t={TIMESTAMP},v1={_sign('')}"
        assert _reason(_verifier(("",)), forged) == "webhook_not_configured"
