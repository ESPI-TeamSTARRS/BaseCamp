from typing import Any

import httpx

from app.account_orders.domain.entities.account_profile import AccountProfile
from app.account_orders.domain.interfaces.account_profile_directory import AccountProfileDirectory


class HttpAccountProfileDirectory(AccountProfileDirectory):
    """Lit `GET /me` d'`auth` avec le jeton du client (reseau interne, delais courts)."""

    def __init__(self, client: httpx.Client, url: str) -> None:
        self._client = client
        self._url = url

    def profile_of(self, token: str) -> AccountProfile | None:
        try:
            response = self._client.get(self._url, headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            body: Any = response.json()
            email = body["email"]
            verified = body["email_verified"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        if not isinstance(email, str) or not email or not isinstance(verified, bool):
            return None
        return AccountProfile(email, verified)
