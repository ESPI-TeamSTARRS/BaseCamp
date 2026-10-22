"""Commande d'exploitation `create-operator-invite` : invite une personne a devenir operateur.

  python -m app.backoffice.create_operator_invite --email ops@example.com

Reservee a un administrateur IT avec acces a la VM (aucune route de l'application ne cree d'invitation).
Affiche UN lien a usage unique, valable 5 minutes au plus, lie a l'adresse : l'administrateur le remet
a la personne (pas d'envoi par email). La personne y choisit son mot de passe et enregistre son visage.
Seule l'empreinte du jeton est stockee : le lien ne se retrouve plus apres cet affichage.

Exemple (pile Docker) :
  docker compose exec -T auth python -m app.backoffice.create_operator_invite --email ops@example.com
"""

import argparse
import sys

from sqlalchemy import Engine, create_engine

from app.backoffice.application.create_operator_invitation import (
    CreateOperatorInvitationUseCase,
    InvitationAddressTakenError,
)
from app.backoffice.composition import build_invitation_creation
from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.registration.domain.exceptions.invalid_email_error import InvalidEmailError

DB_CONNECT_TIMEOUT_SECONDS = 5


def run(use_case: CreateOperatorInvitationUseCase, email: str) -> int:
    """Code de sortie : 0 cree (le lien est la seule sortie utile), 1 refuse (message fixe)."""
    try:
        created = use_case.execute(email)
    except InvalidEmailError:
        print("Adresse email invalide.", file=sys.stderr)
        return 1
    except InvitationAddressTakenError:
        print("Un compte existe déjà avec cette adresse.", file=sys.stderr)
        return 1
    print(f"Lien d'invitation (usage unique, valable jusqu'à {created.expires_at:%H:%M:%S} UTC) :")
    print(created.link)
    return 0


def build(
    engine: Engine, events: BusinessEventLogger, settings: Settings
) -> CreateOperatorInvitationUseCase:
    return build_invitation_creation(settings, engine, events)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Invite un opérateur par un lien à usage unique.")
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
