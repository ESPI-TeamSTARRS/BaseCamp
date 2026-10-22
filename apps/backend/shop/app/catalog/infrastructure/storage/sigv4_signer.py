import hashlib
import hmac
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import quote

_ALGORITHM = "AWS4-HMAC-SHA256"


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


class Sigv4Signer:
    """Signature AWS Signature Version 4 (sans paramètres de requête), pour l'API S3 de SeaweedFS."""

    def __init__(self, access_key: str, secret_key: str, region: str, service: str) -> None:
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._service = service

    def authorization(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        payload_hash: str,
        moment: datetime,
    ) -> str:
        """En-tête `Authorization` pour ces en-têtes (noms en minuscules, tous signés)."""
        moment = moment.astimezone(UTC)
        stamp = moment.strftime("%Y%m%dT%H%M%SZ")
        day = stamp[:8]
        names = sorted(headers)
        canonical_headers = "".join(f"{name}:{headers[name].strip()}\n" for name in names)
        signed_headers = ";".join(names)
        canonical_request = "\n".join(
            [
                method,
                quote(path, safe="/-_.~"),
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        scope = f"{day}/{self._region}/{self._service}/aws4_request"
        to_sign = "\n".join(
            [_ALGORITHM, stamp, scope, hashlib.sha256(canonical_request.encode()).hexdigest()]
        )
        signature = hmac.new(self._signing_key(day), to_sign.encode(), hashlib.sha256).hexdigest()
        return (
            f"{_ALGORITHM} Credential={self._access_key}/{scope},"
            f"SignedHeaders={signed_headers},Signature={signature}"
        )

    def _signing_key(self, day: str) -> bytes:
        key = _hmac(f"AWS4{self._secret_key}".encode(), day)
        return _hmac(_hmac(_hmac(key, self._region), self._service), "aws4_request")
