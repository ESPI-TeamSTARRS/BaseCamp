"""Montage en memoire des trois temps (identifiant, visage, mot de passe), pour les tests."""

from datetime import timedelta

from app.backoffice.__tests__.fakes import (
    PNG,
    BackofficeStore,
    FakeBackofficeUnitOfWork,
    FakeChallengeTokenGenerator,
)
from app.backoffice.application.identify_operator import IdentifyOperatorUseCase
from app.backoffice.application.verify_face import VerifyFaceUseCase
from app.backoffice.application.verify_operator_password import VerifyOperatorPasswordUseCase
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import (
    FakeReconnaissanceFaciale,
)
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.config import Settings
from app.lockout.__tests__.fakes import FakeLockoutUnitOfWork, LockoutStore
from app.lockout.application.lockout_service import LockoutService
from app.lockout.composition import build_lockout_policies
from app.login.__tests__.fakes import (
    FakeAccessTokenSigner,
    FakeClock,
    FakeEmailFingerprinter,
    FakePasswordVerifier,
    FakeStore,
    FakeUnitOfWork,
    make_account,
)
from app.login.domain.entities.account import Account

OPERATOR_EMAIL = "operateur@example.com"
OPERATOR_SECRET = "sentier-du-mont-blanc"
WRONG_SECRET = "mauvais-mot-de-passe"
ADDRESS = "203.0.113.9"
TTL = 120
ACCESS_TTL = 900


class Flow:
    def __init__(self, recognizer: FakeReconnaissanceFaciale | None = None) -> None:
        self.operator: Account = make_account(OPERATOR_EMAIL, OPERATOR_SECRET, role="operator")
        self.customer: Account = make_account("client@example.com", role="customer")
        self.accounts = FakeStore(self.operator, self.customer)
        self.store = BackofficeStore()
        self.lockouts = LockoutStore()
        self.events = InMemoryBusinessEventLogger()
        self.clock = FakeClock()
        self.verifier = FakePasswordVerifier()
        self.signer = FakeAccessTokenSigner()
        self.recognizer = recognizer or FakeReconnaissanceFaciale()
        self.tokens = FakeChallengeTokenGenerator()
        fingerprinter = FakeEmailFingerprinter()
        lockout = LockoutService(
            lambda: FakeLockoutUnitOfWork(self.lockouts),
            build_lockout_policies(Settings()),
            self.events,
        )

        def accounts() -> FakeUnitOfWork:
            return FakeUnitOfWork(self.accounts)

        def backoffice() -> FakeBackofficeUnitOfWork:
            return FakeBackofficeUnitOfWork(self.store)

        self.identify = IdentifyOperatorUseCase(
            accounts, backoffice, self.tokens, fingerprinter, self.clock, self.events, TTL
        )
        self.face = VerifyFaceUseCase(
            backoffice, self.tokens, self.recognizer, lockout, self.clock, self.events
        )
        self.password = VerifyOperatorPasswordUseCase(
            accounts,
            backoffice,
            self.tokens,
            self.verifier,
            self.signer,
            lockout,
            self.clock,
            self.events,
            ACCESS_TTL,
        )
        self.lockout = lockout
        self.enroll(self.operator, PNG)

    def enroll(self, account: Account, photo: bytes) -> None:
        self.store.templates[account.id] = self.recognizer.enroler([photo])

    def tick(self, seconds: int = 10) -> None:
        self.clock.current += timedelta(seconds=seconds)
