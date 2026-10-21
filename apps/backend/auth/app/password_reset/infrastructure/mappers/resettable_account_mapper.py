from app.password_reset.domain.entities.resettable_account import ResettableAccount
from app.registration.domain.value_objects.email_address import EmailAddress
from app.registration.infrastructure.models.user_model import UserModel


class ResettableAccountMapper:
    @staticmethod
    def to_entity(model: UserModel) -> ResettableAccount:
        return ResettableAccount(model.id, EmailAddress.of(model.email))
