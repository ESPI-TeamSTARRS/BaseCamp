from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.registration.domain.enums.user_role import UserRole
from app.registration.domain.value_objects.email_address import EmailAddress


@dataclass(frozen=True)
class User:
    id: UUID
    email: EmailAddress
    password_hash: str = field(repr=False)
    role: UserRole
    email_verified_at: datetime | None
    created_at: datetime

    @classmethod
    def register(cls, email: EmailAddress, password_hash: str, now: datetime) -> "User":
        return cls(uuid4(), email, password_hash, UserRole.CUSTOMER, None, now)
