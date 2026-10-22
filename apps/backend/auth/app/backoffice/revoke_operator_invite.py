"""Commande d'exploitation `revoke-operator-invite` : revoque les invitations d'une adresse.

  python -m app.backoffice.revoke_operator_invite --email ops@example.com

Revoque les invitations encore utilisables de l'adresse (lien perdu, mal transmis ou divulgue).
"""

import argparse
import sys

from sqlalchemy import Engine, create_engine

from app.backoffice.application.revoke_operator_invitation import (
    RevokeOperatorInvitationUseCase,
)
from app.backoffice.composition import build_invitation_revocation
from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.registration.domain.exceptions.invalid_email_error import InvalidEmailError

DB_CONNECT_TIMEOUT_SECONDS = 5


def run(use_case: RevokeOperatorInvitationUseCase, email: str) -> int:
    """Code de sortie : 0 (meme s'il n'y avait rien a revoquer, dit clairement), 1 adresse invalide."""
    try:
        revoked = use_case.execute(email)
    except InvalidEmailError:
        print("Adresse email invalide.", file=sys.stderr)
        return 1
    if revoked:
        print(f"{revoked} invitation(s) révoquée(s).")
    else:
        print("Aucune invitation utilisable pour cette adresse.")
    return 0


def build(
    engine: Engine, events: BusinessEventLogger, settings: Settings
) -> RevokeOperatorInvitationUseCase:
    return build_invitation_revocation(settings, engine, events)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Révoque les invitations d'un opérateur.")
    parser.add_argument("--email", required=True)
    arguments = parser.parse_args(argv)
    settings = Settings()
    engine = create_engine(
        settings.database_url, connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS}
    )
    events = StructlogBusinessEventLogger(settings.service_name, sys.stdout)
    try:
        use_case = build(engine, events, settings)
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return run(use_case, arguments.email)


if __name__ == "__main__":
    raise SystemExit(main())
