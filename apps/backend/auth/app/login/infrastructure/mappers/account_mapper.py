from app.login.domain.entities.account import Account
from app.login.infrastructure.models.account_model import AccountModel


class AccountMapper:
    @staticmethod
    def to_entity(model: AccountModel) -> Account:
        return Account(
            id=model.id,
            email=model.email,
            password_hash=model.password_hash,
            role=model.role,
            email_verified=model.email_verified_at is not None,
            disabled=model.disabled_at is not None,
        )
