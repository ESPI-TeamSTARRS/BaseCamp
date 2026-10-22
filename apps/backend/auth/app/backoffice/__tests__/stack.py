"""Application reelle (routes, crypto, SQL) sur SQLite en memoire pour les tests du back-office."""

import base64
from uuid import UUID

from httpx import AsyncClient, Response
from sqlalchemy import text

from app.backoffice.__tests__.fakes import PNG
from app.backoffice.application.identify_operator import IdentifyOperatorUseCase
from app.backoffice.application.verify_face import VerifyFaceUseCase
from app.backoffice.application.verify_operator_password import VerifyOperatorPasswordUseCase
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import (
    FakeReconnaissanceFaciale,
)
from app.backoffice.infrastructure.clients.secure_challenge_token_generator import (
    SecureChallengeTokenGenerator,
)
from app.backoffice.infrastructure.repositories.sqlalchemy_backoffice_unit_of_work import (
    SqlAlchemyBackofficeUnitOfWork,
)
from app.backoffice.presentation.router import router
from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.lockout.application.lockout_service import LockoutService
from app.lockout.composition import build_lockout_policies
from app.lockout.infrastructure.repositories.sqlalchemy_lockout_unit_of_work import (
    SqlAlchemyLockoutUnitOfWork,
)
from app.login.__tests__.fakes import FakeEmailFingerprinter
from app.login.__tests__.stack import ACCOUNT_SECRET, AUDIENCE, ISSUER, LoginStack
from app.login.infrastructure.clients.jwt_access_token_signer import JwtAccessTokenSigner
from app.login.infrastructure.repositories.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork

OPERATOR_EMAIL = "operateur@example.com"
WRONG = "mauvais-mot-de-passe"
CHALLENGE_TTL = 120


def b64(image: bytes) -> str:
    return base64.b64encode(image).decode()


class BackofficeStack(LoginStack):
    """Le back-office monte sur la pile de connexion : memes comptes, memes cles, meme horloge."""

    def __init__(self, events: BusinessEventLogger) -> None:
        super().__init__(events)
        self.recognizer = FakeReconnaissanceFaciale()
        self.operator_id: UUID = self.add_account(OPERATOR_EMAIL, role="operator")
        self.customer_id: UUID = self.add_account("client@example.com")
        self.enroll(self.operator_id, PNG)

        def unit_of_work() -> SqlAlchemyBackofficeUnitOfWork:
            return SqlAlchemyBackofficeUnitOfWork(self.engine)

        def accounts() -> SqlAlchemyUnitOfWork:
            return SqlAlchemyUnitOfWork(self.engine)

        tokens = SecureChallengeTokenGenerator()
        lockout = LockoutService(
            lambda: SqlAlchemyLockoutUnitOfWork(self.engine),
            build_lockout_policies(Settings()),
            events,
        )
        fingerprinter = FakeEmailFingerprinter()
        self.application.state.identify_operator_use_case = IdentifyOperatorUseCase(
            accounts, unit_of_work, tokens, fingerprinter, self.clock, events, CHALLENGE_TTL
        )
        self.application.state.verify_face_use_case = VerifyFaceUseCase(
            unit_of_work, tokens, self.recognizer, lockout, self.clock, events
        )
        self.application.state.verify_operator_password_use_case = VerifyOperatorPasswordUseCase(
            accounts,
            unit_of_work,
            tokens,
            self.verifier,
            JwtAccessTokenSigner(self.keys, ISSUER, AUDIENCE),
            lockout,
            self.clock,
            events,
            900,
        )
        self.application.include_router(router)

    def enroll(self, account_id: UUID, photo: bytes) -> None:
        with SqlAlchemyBackofficeUnitOfWork(self.engine) as work:
            work.templates.save(account_id, self.recognizer.enroler([photo]), self.clock.now())
            work.commit()

    def rows(self, sql: str) -> list[tuple[object, ...]]:
        with self.engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(sql))]

    def row(self, sql: str) -> tuple[object, ...]:
        (only,) = self.rows(sql)
        return only

    def exec(self, sql: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(text(sql))

    # --- appels HTTP des trois temps ---
    @staticmethod
    async def identify(client: AsyncClient, email: str = OPERATOR_EMAIL) -> Response:
        return await client.post("/backoffice/identify", json={"email": email})

    @staticmethod
    async def face(client: AsyncClient, challenge: str, *images: bytes) -> Response:
        return await client.post(
            "/backoffice/face",
            json={
                "challenge_id": challenge,
                "images": [b64(image) for image in (images or (PNG,))],
            },
        )

    @staticmethod
    async def password(
        client: AsyncClient, challenge: str, password: str = ACCOUNT_SECRET
    ) -> Response:
        return await client.post(
            "/backoffice/password", json={"challenge_id": challenge, "password": password}
        )

    async def until_face_ok(self, client: AsyncClient, email: str = OPERATOR_EMAIL) -> str:
        challenge = str((await self.identify(client, email)).json()["challenge_id"])
        assert (await self.face(client, challenge)).status_code == 200
        return challenge
