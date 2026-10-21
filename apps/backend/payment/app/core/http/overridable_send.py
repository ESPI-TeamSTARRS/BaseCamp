import json
from typing import Any

Message = dict[str, Any]


class OverridableSend:
    """Enveloppe de `send` qui permet de remplacer la réponse de l'application par une erreur.

    FastAPI convertit toute exception levée pendant la lecture du corps en 400 : un garde-fou
    qui veut imposer 408 ou 413 pose donc un remplacement, et la première réponse émise par
    l'application est alors substituée (le reste est ignoré).
    """

    def __init__(self, send: Any) -> None:
        self._send = send
        self._started = False
        self._override: tuple[int, bytes, list[tuple[bytes, bytes]]] | None = None
        self._sent_override = False

    @property
    def started(self) -> bool:
        return self._started or self._sent_override

    @property
    def overridden(self) -> bool:
        return self._override is not None

    def override(
        self, status: int, detail: str, headers: list[tuple[bytes, bytes]] | None = None
    ) -> None:
        if self.started or self._override is not None:
            return
        body = json.dumps({"detail": detail}).encode()
        self._override = (status, body, headers or [])

    async def __call__(self, message: Message) -> None:
        if self._override is not None:
            if message["type"] == "http.response.start":
                await self.flush()
            return
        if message["type"] == "http.response.start":
            self._started = True
        await self._send(message)

    async def flush(self) -> None:
        """Émet la réponse de remplacement si l'application n'a rien envoyé."""
        if self._override is None or self._sent_override:
            return
        status, body, extra = self._override
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            *extra,
        ]
        self._sent_override = True
        await self._send({"type": "http.response.start", "status": status, "headers": headers})
        await self._send({"type": "http.response.body", "body": body})
