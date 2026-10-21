import hashlib
import hmac
from collections.abc import Callable, Sequence

from app.payment_confirmation.domain.errors.invalid_webhook_signature_error import (
    InvalidWebhookSignatureError,
)


class WebhookSignatureVerifier:
    """Vérifie `t=<secondes>,v1=<hex>` : HMAC-SHA256(secret, "<t>.<corps brut>"), en temps constant."""

    def __init__(
        self, secrets: Sequence[str], tolerance_seconds: int, clock: Callable[[], float]
    ) -> None:
        self._secrets = tuple(secret.encode() for secret in secrets if secret)
        self._tolerance = tolerance_seconds
        self._clock = clock

    def verify(self, header: str | None, raw_body: bytes) -> None:
        if not self._secrets:
            raise InvalidWebhookSignatureError("webhook_not_configured")
        if not header:
            raise InvalidWebhookSignatureError("signature_missing")
        timestamp, signatures = self._parse(header)
        if abs(self._clock() - timestamp) > self._tolerance:
            raise InvalidWebhookSignatureError("timestamp_out_of_window")
        signed = f"{timestamp}.".encode() + raw_body
        for secret in self._secrets:
            expected = hmac.new(secret, signed, hashlib.sha256).hexdigest()
            for received in signatures:
                if hmac.compare_digest(expected, received):
                    return
        raise InvalidWebhookSignatureError("signature_mismatch")

    @staticmethod
    def _parse(header: str) -> tuple[int, list[str]]:
        timestamp: int | None = None
        signatures: list[str] = []
        for part in header.split(","):
            key, _, value = part.strip().partition("=")
            if key == "t" and value.isascii() and value.isdigit():
                timestamp = int(value)
            elif key == "v1" and value:
                signatures.append(value)
        if timestamp is None or not signatures:
            raise InvalidWebhookSignatureError("signature_malformed")
        return timestamp, signatures
