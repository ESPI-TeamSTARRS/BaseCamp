from collections.abc import Callable

from app.password_reset.domain.interfaces.password_reset_unit_of_work import (
    PasswordResetUnitOfWork,
)

UnitOfWorkFactory = Callable[[], PasswordResetUnitOfWork]
