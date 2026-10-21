from uuid import UUID

from pydantic import BaseModel


class ProfileResponse(BaseModel):
    id: UUID
    email: str
    roles: list[str]
    email_verified: bool
