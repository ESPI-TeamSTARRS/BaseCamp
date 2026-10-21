from typing import cast

from fastapi import Request

from app.admin.application.change_account_status import ChangeAccountStatusUseCase
from app.admin.application.list_accounts import ListAccountsUseCase


def get_list_accounts_use_case(request: Request) -> ListAccountsUseCase:
    """Les cas d'usage sont cables dans composition.py (la presentation n'importe pas l'infrastructure)."""
    return cast(ListAccountsUseCase, request.app.state.list_accounts_use_case)


def get_change_account_status_use_case(request: Request) -> ChangeAccountStatusUseCase:
    return cast(ChangeAccountStatusUseCase, request.app.state.change_account_status_use_case)
