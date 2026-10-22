from collections.abc import Callable

from app.backoffice.domain.interfaces.backoffice_unit_of_work import BackofficeUnitOfWork

UnitOfWorkFactory = Callable[[], BackofficeUnitOfWork]
