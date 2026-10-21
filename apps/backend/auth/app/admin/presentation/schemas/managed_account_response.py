from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ManagedAccountResponse(BaseModel):
    id: UUID
    email: str
    role: str
    email_verified: bool
    disabled: bool
    created_at: datetime
