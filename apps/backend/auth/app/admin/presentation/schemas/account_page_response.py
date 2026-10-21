from pydantic import BaseModel

from app.admin.presentation.schemas.managed_account_response import ManagedAccountResponse


class AccountPageResponse(BaseModel):
    items: list[ManagedAccountResponse]
    total: int
    limit: int
    offset: int
