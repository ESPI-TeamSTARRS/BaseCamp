from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.admin.application.account_summary import AccountSummary
from app.admin.application.change_account_status import ChangeAccountStatusUseCase
from app.admin.application.list_accounts import MAX_PAGE_SIZE, ListAccountsUseCase
from app.admin.presentation.dependencies import (
    get_change_account_status_use_case,
    get_list_accounts_use_case,
)
from app.admin.presentation.schemas.account_page_response import AccountPageResponse
from app.admin.presentation.schemas.managed_account_response import ManagedAccountResponse
from app.login.application.principal import Principal
from app.login.presentation.dependencies import client_ip
from app.login.presentation.require_role import require_role

OPERATOR = "operator"
NO_STORE = "no-store"

# Chaque route exige le role `operator` lu dans le jeton signe : sans jeton 401, sans le role 403.
router = APIRouter(prefix="/admin", tags=["admin"])


def _response(account: AccountSummary) -> ManagedAccountResponse:
    return ManagedAccountResponse(
        id=account.id,
        email=account.email,
        role=account.role,
        email_verified=account.email_verified,
        disabled=account.disabled,
        created_at=account.created_at,
    )


@router.get("/users", response_model=AccountPageResponse)
def list_users(
    request: Request,
    response: Response,
    operator: Annotated[Principal, Depends(require_role(OPERATOR))],
    use_case: Annotated[ListAccountsUseCase, Depends(get_list_accounts_use_case)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AccountPageResponse:
    page = use_case.execute(operator.id, limit, offset, client_ip(request))
    response.headers["Cache-Control"] = NO_STORE
    return AccountPageResponse(
        items=[_response(account) for account in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("/users/{account_id}/disable", response_model=ManagedAccountResponse)
def disable_user(
    account_id: UUID,
    request: Request,
    response: Response,
    operator: Annotated[Principal, Depends(require_role(OPERATOR))],
    use_case: Annotated[ChangeAccountStatusUseCase, Depends(get_change_account_status_use_case)],
) -> ManagedAccountResponse:
    account = use_case.disable(operator.id, account_id, client_ip(request))
    response.headers["Cache-Control"] = NO_STORE
    return _response(account)


@router.post("/users/{account_id}/enable", response_model=ManagedAccountResponse)
def enable_user(
    account_id: UUID,
    request: Request,
    response: Response,
    operator: Annotated[Principal, Depends(require_role(OPERATOR))],
    use_case: Annotated[ChangeAccountStatusUseCase, Depends(get_change_account_status_use_case)],
) -> ManagedAccountResponse:
    account = use_case.enable(operator.id, account_id, client_ip(request))
    response.headers["Cache-Control"] = NO_STORE
    return _response(account)
