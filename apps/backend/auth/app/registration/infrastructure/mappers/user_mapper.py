from app.registration.domain.entities.user import User
from app.registration.infrastructure.models.user_model import UserModel


class UserMapper:
    @staticmethod
    def to_model(user: User) -> UserModel:
        return UserModel(
            id=user.id,
            email=user.email.value,
            password_hash=user.password_hash,
            role=user.role.value,
            email_verified_at=user.email_verified_at,
            created_at=user.created_at,
        )
