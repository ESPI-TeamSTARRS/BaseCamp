from collections.abc import Callable

from app.registration.domain.interfaces.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]
