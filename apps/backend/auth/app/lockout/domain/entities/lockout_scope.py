from app.lockout.domain.enums.subject_type import SubjectType


def lockout_scope(step: str, subject_type: SubjectType) -> str:
    """Cle de stockage d'un compteur.

    L'etape seule pour un compte (compatible avec les lignes existantes), `etape@address` pour une
    adresse source : les compteurs ne se melangent jamais.
    """
    if subject_type is SubjectType.ACCOUNT:
        return step
    return f"{step}@{subject_type.value}"
