"""Application reelle (routes, crypto, SQL) sur SQLite en memoire pour les tests d'administration."""

from uuid import UUID

from httpx import AsyncClient

from app.admin.application.change_account_status import ChangeAccountStatusUseCase
from app.admin.application.list_accounts import ListAccountsUseCase
from app.admin.infrastructure.repositories.sqlalchemy_admin_unit_of_work import (
    SqlAlchemyAdminUnitOfWork,
)
from app.core.events.business_event_logger import BusinessEventLogger
from app.login.__tests__.stack import (
    ACCOUNT_SECRET,
    AUDIENCE,
    EMAIL,
    ISSUER,
    LoginStack,
)
from app.login.domain.entities.access_token_claims import AccessTokenClaims
from app.login.infrastructure.clients.jwt_access_token_signer import JwtAccessTokenSigner
from app.login.infrastructure.repositories.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from app.registration.infrastructure.clients.system_clock import SystemClock

OPERATOR_EMAIL = "operateur@example.com"
OTHER_OPERATOR_EMAIL = "operateur2@example.com"


class AdminStack(LoginStack):
    def __init__(self, events: BusinessEventLogger) -> None:
        super().__init__(events)

        def factory() -> SqlAlchemyAdminUnitOfWork:
            return SqlAlchemyAdminUnitOfWork(self.engine)

        self.application.state.list_accounts_use_case = ListAccountsUseCase(factory, events)
        self.application.state.change_account_status_use_case = ChangeAccountStatusUseCase(
            factory, SystemClock(), events
        )
        self.operator_id: UUID = self.add_account(OPERATOR_EMAIL, role="operator")
        self.customer_id: UUID = self.add_account(EMAIL)

    async def token_of(self, client: AsyncClient, email: str) -> dict[str, str]:
        """Jeton de l'operateur tel que la connexion en trois temps l'emet (le login classique ne
        delivre plus le role `operator`) ; pour un autre compte, le login classique."""
        with SqlAlchemyUnitOfWork(self.engine) as work:
            account = work.accounts.find_by_email(email)
        if account is not None and account.role == "operator":
            claims = AccessTokenClaims.issue_operator(account, self.clock.now(), 900, "jti-test")
            signer = JwtAccessTokenSigner(self.keys, ISSUER, AUDIENCE)
            return {"Authorization": f"Bearer {signer.sign(claims)}"}
        response = await client.post("/login", json={"email": email, "password": ACCOUNT_SECRET})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
