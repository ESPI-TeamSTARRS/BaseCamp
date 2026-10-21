import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx

from app.catalog.domain.errors.image_storage_error import ImageStorageError
from app.catalog.domain.interfaces.product_image_storage import ProductImageStorage
from app.catalog.infrastructure.storage.sigv4_signer import Sigv4Signer


def _utc_now() -> datetime:
    return datetime.now(UTC)


class S3ProductImageStorage(ProductImageStorage):
    """Écrit dans le bucket `product-images` par l'API S3 de SeaweedFS (clés S3 lues dans l'environnement)."""

    def __init__(
        self,
        client: httpx.Client,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._client = client
        self._endpoint = endpoint.rstrip("/")
        self._host = urlsplit(endpoint).netloc
        self._bucket = bucket
        self._configured = bool(access_key and secret_key)
        self._signer = Sigv4Signer(access_key, secret_key, region, "s3")
        self._clock = clock

    def store(self, key: str, content: bytes, content_type: str) -> None:
        if not self._configured:
            raise ImageStorageError
        path = f"/{self._bucket}/{key}"
        moment = self._clock()
        payload_hash = hashlib.sha256(content).hexdigest()
        signed = {
            "content-type": content_type,
            "host": self._host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
        }
        headers = {
            **signed,
            "authorization": self._signer.authorization("PUT", path, signed, payload_hash, moment),
        }
        try:
            response = self._client.put(
                f"{self._endpoint}{quote(path, safe='/-_.~')}", content=content, headers=headers
            )
        except httpx.HTTPError:
            raise ImageStorageError from None
        if response.status_code not in (200, 201):
            raise ImageStorageError
