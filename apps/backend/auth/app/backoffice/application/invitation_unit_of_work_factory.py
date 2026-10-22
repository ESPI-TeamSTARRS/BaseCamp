from collections.abc import Callable

from app.backoffice.domain.interfaces.invitation_unit_of_work import InvitationUnitOfWork

InvitationUnitOfWorkFactory = Callable[[], InvitationUnitOfWork]
