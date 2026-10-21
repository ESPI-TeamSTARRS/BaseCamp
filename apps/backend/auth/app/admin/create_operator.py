"""Commande d'exploitation `create-operator` : `python -m app.admin.create_operator --email <adresse>`.

Seule voie de creation d'un compte `operator` (aucune route HTTP, l'inscription publique ne produit
que `customer`). Le mot de passe est lu dans la variable `OPERATOR_PASSWORD` ou saisi sans echo
(deux fois); il n'est jamais passe en argument, journalise ni affiche.

Exemple (pile Docker) :
  docker compose exec -e OPERATOR_PASSWORD=... auth python -m app.admin.create_operator --email ops@example.com
"""

import argparse
import getpass
import os
import sys
from collections.abc import Mapping

from sqlalchemy import Engine, create_engine

from app.admin.composition import build_create_operator
from app.admin.domain.exceptions.admin_errors import OperatorAlreadyExistsError
from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.registration.domain.exceptions.invalid_email_error import InvalidEmailError
from app.registration.domain.exceptions.weak_password_error import WeakPasswordError

DB_CONNECT_TIMEOUT_SECONDS = 5
PASSWORD_VARIABLE = "OPERATOR_PASSWORD"  # noqa: S105


def read_password(environ: Mapping[str, str]) -> str:
    """Variable d'environnement, sinon saisie masquee confirmee."""
    from_env = environ.get(PASSWORD_VARIABLE)
    if from_env:
        return from_env
    first = getpass.getpass("Mot de passe : ")
    if first != getpass.getpass("Confirmez le mot de passe : "):
        raise ValueError("Les deux saisies different.")
    return first


def run(
    engine: Engine,
    events: BusinessEventLogger,
    email: str,
    environ: Mapping[str, str],
) -> int:
    """Code de sortie : 0 cree, 1 refuse (message fixe sur stderr, jamais le mot de passe)."""
    try:
        password = read_password(environ)
        account_id = build_create_operator(engine, events).execute(email, password)
    except InvalidEmailError:
        print("Adresse email invalide.", file=sys.stderr)
        return 1
    except WeakPasswordError as error:
        print(error.message, file=sys.stderr)
        return 1
    except OperatorAlreadyExistsError as error:
        print(error.message, file=sys.stderr)
        return 1
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"Opérateur créé : {account_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crée un compte opérateur.")
    parser.add_argument("--email", required=True)
    arguments = parser.parse_args(argv)
    settings = Settings()
    engine = create_engine(
        settings.database_url, connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS}
    )
    return run(
        engine,
        StructlogBusinessEventLogger(settings.service_name, sys.stdout),
        arguments.email,
        os.environ,
    )


if __name__ == "__main__":
    raise SystemExit(main())
