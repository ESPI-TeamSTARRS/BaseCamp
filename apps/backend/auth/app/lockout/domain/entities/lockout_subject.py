from dataclasses import dataclass

from app.lockout.domain.enums.subject_type import SubjectType


@dataclass(frozen=True)
class LockoutSubject:
    """Un compteur designe : etape, empreinte opaque du sujet et type de sujet."""

    step: str
    subject: str
    subject_type: SubjectType = SubjectType.ACCOUNT
