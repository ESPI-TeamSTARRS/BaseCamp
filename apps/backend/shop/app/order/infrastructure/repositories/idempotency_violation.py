from sqlalchemy.exc import IntegrityError

IDEMPOTENCY_COLUMN = "idempotency_key"


def is_idempotency_violation(error: IntegrityError) -> bool:
    """Vrai si l'echec vient de l'unicite de la cle d'idempotence (SQLite et Postgres)."""
    return IDEMPOTENCY_COLUMN in str(error.orig)
