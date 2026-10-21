from collections.abc import Callable

from app.login.domain.interfaces.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]
