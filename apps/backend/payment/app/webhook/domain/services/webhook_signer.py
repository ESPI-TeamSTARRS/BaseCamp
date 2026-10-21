import hashlib
import hmac
from collections.abc import Sequence

TOLERANCE_SECONDS = 300


class WebhookSigner:
    """Signe et vérifie `X-Payment-Signature: t=<secondes>,v1=<HMAC-SHA256 de "<t>.<corps>">`.

    Plusieurs secrets signent le même message (rotation) : l'en-tête porte alors un `v1` par
    secret et le récepteur accepte dès qu'un seul correspond. La comparaison est en temps
    constant et le message vérifié inclut l'horodatage, donc impossible à rejouer hors fenêtre.
    """

    def __init__(self, secrets: Sequence[str]) -> None:
        if not secrets or not all(secrets):
            raise ValueError("at least one non-empty secret is required")
        self._secrets = tuple(secrets)

    def __repr__(self) -> str:
        return f"WebhookSigner(secrets={len(self._secrets)})"

    def header(self, timestamp: int, body: str) -> str:
        signatures = ",".join(
            f"v1={self._sign(secret, timestamp, body)}" for secret in self._secrets
        )
        return f"t={timestamp},{signatures}"

    def verify(
        self, header: str, body: str, now: int, tolerance_seconds: int = TOLERANCE_SECONDS
    ) -> bool:
        timestamp, received = self._parse(header)
        if timestamp is None or not received:
            return False
        if abs(now - timestamp) > tolerance_seconds:
            return False
        matches = [
            hmac.compare_digest(self._sign(secret, timestamp, body), signature)
            for secret in self._secrets
            for signature in received
        ]
        return any(matches)

    @staticmethod
    def _sign(secret: str, timestamp: int, body: str) -> str:
        message = f"{timestamp}.{body}".encode()
        return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

    @staticmethod
    def _parse(header: str) -> tuple[int | None, list[str]]:
        timestamp: int | None = None
        signatures: list[str] = []
        for part in header.split(","):
            name, _, value = part.strip().partition("=")
            if name == "t" and value.isdigit():
                timestamp = int(value)
            elif name == "v1" and value:
                signatures.append(value)
        return timestamp, signatures
