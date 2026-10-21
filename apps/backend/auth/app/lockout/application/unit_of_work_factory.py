from collections.abc import Callable

from app.lockout.domain.interfaces.lockout_unit_of_work import LockoutUnitOfWork

UnitOfWorkFactory = Callable[[], LockoutUnitOfWork]
