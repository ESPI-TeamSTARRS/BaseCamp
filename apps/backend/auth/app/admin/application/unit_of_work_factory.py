from collections.abc import Callable

from app.admin.domain.interfaces.admin_unit_of_work import AdminUnitOfWork

UnitOfWorkFactory = Callable[[], AdminUnitOfWork]
