"""Montage en memoire de l'invitation d'operateur (creation, completion, revocation), pour les tests.

La transaction est simulee : sans `commit()`, tout ce qui a ete ecrit est annule en sortie du bloc
(c'est ce qui prouve « compte non cree, jeton non consomme » sur un echec).
"""

import copy
import hashlib
from datetime import datetime, timedelta
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from app.admin.domain.exceptions.admin_errors import OperatorAlreadyExistsError
from app.backoffice.__tests__.fakes import FakeChallengeTokenGenerator
from app.backoffice.application.complete_operator_invitation import (
    CompleteOperatorInvitationUseCase,
)
from app.backoffice.application.create_operator_invitation import (
    CreateOperatorInvitationUseCase,
)
from app.backoffice.application.revoke_operator_invitation import (
    RevokeOperatorInvitationUseCase,
)
from app.backoffice.domain.entities.operator_invitation import OperatorInvitation
from app.backoffice.domain.interfaces.face_template_repository import FaceTemplateRepository
from app.backoffice.domain.interfaces.invitation_repository import InvitationRepository
from app.backoffice.domain.interfaces.invitation_unit_of_work import InvitationUnitOfWork
from app.backoffice.domain.interfaces.operator_account_writer import OperatorAccountWriter
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import (
    FakeReconnaissanceFaciale,
)
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.config import Settings
from app.lockout.__tests__.fakes import FakeLockoutUnitOfWork, LockoutStore
from app.lockout.application.lockout_service import LockoutService
from app.lockout.composition import build_lockout_policies
from app.login.__tests__.fakes import FakeClock, FakeEmailFingerprinter, FakeStore, FakeUnitOfWork
from app.login.domain.entities.account import Account
from app.registration.__tests__.fakes import FakeCommonPasswordList, FakePasswordHasher
from app.registration.domain.services.password_policy import PasswordPolicy

INVITED = "nouvel.operateur@example.com"
GOOD_PASSWORD = "sentier-" + uuid4().hex
ADDRESS = "203.0.113.9"
BASE_URL = "https://mercure.exemple.test"


class InvitationStore:
    def __init__(self, accounts: FakeStore) -> None:
        self.accounts = accounts
        self.invitations: dict[str, OperatorInvitation] = {}
        self.templates: dict[UUID, bytes] = {}
        self.commits = 0

    def snapshot(self) -> tuple[object, object, object]:
        return (
            dict(self.invitations),
            dict(self.templates),
            copy.copy(self.accounts.accounts),
        )

    def restore(self, saved: tuple[object, object, object]) -> None:
        self.invitations, self.templates, self.accounts.accounts = saved  # type: ignore[assignment]


class _Invitations(InvitationRepository):
    def __init__(self, store: InvitationStore) -> None:
        self._store = store

    def add(self, invitation: OperatorInvitation) -> None:
        self._store.invitations[invitation.digest] = invitation

    def find(self, digest: str) -> OperatorInvitation | None:
        return self._store.invitations.get(digest)

    def claim(self, digest: str, now: datetime) -> OperatorInvitation | None:
        invitation = self._store.invitations.get(digest)
        return invitation if invitation is not None and invitation.usable(now) else None

    def mark_consumed(self, digest: str, now: datetime) -> None:
        self._store.invitations[digest] = self._store.invitations[digest].consumed(now)

    def revoke_active_for(self, email: str, now: datetime) -> int:
        count = 0
        for digest, invitation in list(self._store.invitations.items()):
            if invitation.email == email and invitation.usable(now):
                self._store.invitations[digest] = OperatorInvitation(
                    invitation.digest,
                    invitation.email,
                    invitation.created_at,
                    invitation.expires_at,
                    invitation.consumed_at,
                    now,
                )
                count += 1
        return count

    def purge_before(self, cutoff: datetime) -> int:
        stale = [d for d, i in self._store.invitations.items() if i.expires_at < cutoff]
        for digest in stale:
            del self._store.invitations[digest]
        return len(stale)


class _Operators(OperatorAccountWriter):
    def __init__(self, store: InvitationStore) -> None:
        self._store = store

    def add_operator(self, account_id: UUID, email: str, password_hash: str, now: datetime) -> None:
        if any(a.email == email for a in self._store.accounts.accounts.values()):
            raise OperatorAlreadyExistsError
        self._store.accounts.accounts[account_id] = Account(
            account_id, email, password_hash, "operator", True, False
        )


class _Templates(FaceTemplateRepository):
    def __init__(self, store: InvitationStore) -> None:
        self._store = store

    def find(self, account_id: UUID) -> bytes | None:
        return self._store.templates.get(account_id)

    def save(self, account_id: UUID, template: bytes, now: datetime) -> None:
        self._store.templates[account_id] = template


class FakeInvitationUnitOfWork(InvitationUnitOfWork):
    def __init__(self, store: InvitationStore) -> None:
        self._store = store
        self._saved = store.snapshot()
        self._committed = False
        self.invitations = _Invitations(store)
        self.operators = _Operators(store)
        self.templates = _Templates(store)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._committed:
            self._store.restore(self._saved)

    def commit(self) -> None:
        self._committed = True
        self._store.commits += 1


class InvitationFlow:
    def __init__(self, recognizer: FakeReconnaissanceFaciale | None = None) -> None:
        self.accounts = FakeStore()
        self.store = InvitationStore(self.accounts)
        self.lockouts = LockoutStore()
        self.events = InMemoryBusinessEventLogger()
        self.clock = FakeClock()
        self.recognizer = recognizer or FakeReconnaissanceFaciale()
        self.hasher = FakePasswordHasher()
        self.tokens = FakeChallengeTokenGenerator()
        fingerprinter = FakeEmailFingerprinter()
        lockout = LockoutService(
            lambda: FakeLockoutUnitOfWork(self.lockouts),
            build_lockout_policies(Settings()),
            self.events,
        )
        factory = lambda: FakeInvitationUnitOfWork(self.store)  # noqa: E731
        self.create = CreateOperatorInvitationUseCase(
            lambda: FakeUnitOfWork(self.accounts),
            factory,
            self.tokens,
            fingerprinter,
            self.clock,
            self.events,
            BASE_URL,
            300,
        )
        self.revoke = RevokeOperatorInvitationUseCase(
            factory, fingerprinter, self.clock, self.events
        )
        self.complete = CompleteOperatorInvitationUseCase(
            factory,
            self.tokens,
            PasswordPolicy(FakeCommonPasswordList()),
            self.hasher,
            self.recognizer,
            lockout,
            fingerprinter,
            self.clock,
            self.events,
        )

    def invite(self, email: str = INVITED) -> str:
        """Cree l'invitation et rend le JETON (extrait du lien, comme le fait l'administrateur)."""
        created = self.create.execute(email)
        return created.link.split("#token=", 1)[1]

    def tick(self, seconds: int) -> None:
        self.clock.current += timedelta(seconds=seconds)


def digest_of(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
