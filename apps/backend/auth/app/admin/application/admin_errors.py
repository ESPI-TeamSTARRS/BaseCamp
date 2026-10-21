"""Erreurs de l'administration exposees a la presentation (qui n'importe pas le domaine)."""

from app.admin.domain.exceptions.admin_errors import (
    AccountNotFoundError,
    AdminError,
    CannotDisableLastOperatorError,
    CannotDisableSelfError,
    OperatorAlreadyExistsError,
)

__all__ = [
    "AccountNotFoundError",
    "AdminError",
    "CannotDisableLastOperatorError",
    "CannotDisableSelfError",
    "OperatorAlreadyExistsError",
]
