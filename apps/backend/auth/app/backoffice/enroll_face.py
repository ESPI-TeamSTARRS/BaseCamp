"""Commande d'exploitation `enroll-face` : enrole le visage d'un operateur.

  python -m app.backoffice.enroll_face --email ops@example.com --images photo1.jpg photo2.jpg photo3.jpg

3 a 10 photos JPEG ou PNG, variees (de face, leger tour de tete, expression), lues UNIQUEMENT dans
le dossier des photos (`--directory`, `/photos` par defaut : un nom qui en sort est refuse). Elles sont
lues en memoire; elles ne sont ni copiees, ni ecrites sur disque, ni journalisees : seul le gabarit,
chiffre au repos, est conserve. Sans gabarit, l'operateur ne peut pas se connecter au back-office.

Exemple (pile Docker, photos montees en lecture seule) :
  docker compose run --rm -v ./photos:/photos:ro auth python -m app.backoffice.enroll_face \
      --email ops@example.com --images /photos/1.jpg /photos/2.jpg /photos/3.jpg
"""

import argparse
import os
import sys

from sqlalchemy import Engine, create_engine

from app.backoffice.application.enroll_operator_face import EnrollOperatorFaceUseCase
from app.backoffice.application.enrollment_errors import EnrollmentRefusedError
from app.backoffice.composition import build_enrollment
from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger

DB_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_PHOTOS_DIR = "/photos"  # dossier monte en lecture seule dans le conteneur
MAX_FILE_BYTES = (
    10 * 1024 * 1024
)  # on ne lit jamais plus que ce plafond, meme pour un fichier enorme


def read_photos(names: list[str], directory: str = DEFAULT_PHOTOS_DIR) -> list[bytes]:
    """Lit les photos en memoire, UNIQUEMENT dans `directory` : un nom qui en sort (`..`, chemin
    absolu ailleurs, lien symbolique) est refuse. Un fichier absent ou demesure est une erreur de saisie.
    """
    base = os.path.realpath(directory)
    photos: list[bytes] = []
    for name in names:
        candidate = os.path.realpath(os.path.join(base, name))
        if os.path.commonpath([base, candidate]) != base or candidate == base:
            raise ValueError("Une photo doit etre dans le dossier des photos.")
        try:
            with open(candidate, "rb") as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
        except OSError:
            raise ValueError("Une photo est introuvable ou illisible.") from None
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("Une photo est trop volumineuse.")
        photos.append(data)
    return photos


def run(
    use_case: EnrollOperatorFaceUseCase,
    email: str,
    image_paths: list[str],
    directory: str = DEFAULT_PHOTOS_DIR,
) -> int:
    """Code de sortie : 0 enrole, 1 refuse (message fixe sur stderr, jamais de donnee biometrique)."""
    try:
        account_id = use_case.execute(email, read_photos(image_paths, directory))
    except EnrollmentRefusedError as error:
        print(error.message, file=sys.stderr)
        return 1
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"Visage enrôlé : {account_id}")
    return 0


def build(
    engine: Engine, events: BusinessEventLogger, settings: Settings
) -> EnrollOperatorFaceUseCase:
    return build_enrollment(settings, engine, events)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enrôle le visage d'un opérateur.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--images", required=True, nargs="+", metavar="PHOTO")
    parser.add_argument(
        "--directory",
        default=DEFAULT_PHOTOS_DIR,
        help="dossier des photos (monte en lecture seule); les photos y sont lues, jamais ailleurs",
    )
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
    return run(use_case, arguments.email, arguments.images, arguments.directory)


if __name__ == "__main__":
    raise SystemExit(main())
