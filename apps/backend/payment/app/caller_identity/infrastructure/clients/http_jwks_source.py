from collections.abc import Mapping
from typing import Any

import httpx

from app.caller_identity.domain.exceptions.verification_keys_unavailable_error import (
    VerificationKeysUnavailableError,
)
from app.caller_identity.domain.interfaces.jwks_source import JwksSource

OK_KEY_TYPE = "OKP"  # Ed25519 (RFC 8037)


class HttpJwksSource(JwksSource):
    """Lit le JWKS d'`auth` sur le reseau interne (delais courts : auth arrete ne bloque pas shop)."""

    def __init__(self, client: httpx.Client, url: str) -> None:
        self._client = client
        self._url = url

    def fetch(self) -> Mapping[str, Mapping[str, Any]]:
        try:
            response = self._client.get(self._url)
            response.raise_for_status()
            document = response.json()
            keys = document["keys"]
            if not isinstance(keys, list):
                raise TypeError("keys must be a list")
            return {
                str(key["kid"]): key
                for key in keys
                if isinstance(key, dict) and key.get("kty") == OK_KEY_TYPE and "kid" in key
            }
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise VerificationKeysUnavailableError from None
