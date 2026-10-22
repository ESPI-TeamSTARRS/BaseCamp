"""Doublures en memoire du back-office, partagees par les tests de la tranche et de ses appelants."""

import hashlib
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from app.backoffice.domain.entities.login_challenge import LoginChallenge
from app.backoffice.domain.interfaces.backoffice_unit_of_work import BackofficeUnitOfWork
from app.backoffice.domain.interfaces.challenge_repository import ChallengeRepository
from app.backoffice.domain.interfaces.challenge_token_generator import ChallengeTokenGenerator
from app.backoffice.domain.interfaces.face_template_repository import FaceTemplateRepository

PNG = b"\x89PNG\r\n\x1a\n" + b"visage-de-camille"
OTHER_PNG = b"\x89PNG\r\n\x1a\n" + b"un-autre-visage"
JPEG = b"\xff\xd8\xff\xe0" + b"visage-de-camille-jpeg"


class BackofficeStore:
    def __init__(self) -> None:
        self.challenges: dict[str, LoginChallenge] = {}
        self.templates: dict[UUID, bytes] = {}
        self.commits = 0


class FakeChallengeRepository(ChallengeRepository):
    def __init__(self, store: BackofficeStore) -> None:
        self._store = store

    def add(self, challenge: LoginChallenge) -> None:
        self._store.challenges[challenge.digest] = challenge

    def take(self, digest: str, now: datetime) -> LoginChallenge | None:
        challenge = self._store.challenges.pop(digest, None)
        if challenge is None or challenge.expired(now):
            return None
        return challenge

    def purge_expired(self, now: datetime) -> int:
        stale = [d for d, c in self._store.challenges.items() if c.expired(now)]
        for digest in stale:
            del self._store.challenges[digest]
        return len(stale)


class FakeFaceTemplateRepository(FaceTemplateRepository):
    def __init__(self, store: BackofficeStore) -> None:
        self._store = store

    def find(self, account_id: UUID) -> bytes | None:
        return self._store.templates.get(account_id)

    def save(self, account_id: UUID, template: bytes, now: datetime) -> None:
        self._store.templates[account_id] = template


class FakeBackofficeUnitOfWork(BackofficeUnitOfWork):
    def __init__(self, store: BackofficeStore) -> None:
        self._store = store
        self.challenges = FakeChallengeRepository(store)
        self.templates = FakeFaceTemplateRepository(store)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def commit(self) -> None:
        self._store.commits += 1


class FakeChallengeTokenGenerator(ChallengeTokenGenerator):
    """Identifiants numerotes : `challenge-1`, `challenge-2`, ..."""

    def __init__(self) -> None:
        self.count = 0

    def generate(self) -> str:
        self.count += 1
        return f"challenge-{self.count}"

    def digest(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
