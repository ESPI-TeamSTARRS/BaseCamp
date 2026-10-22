from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from app.core.client_address_resolver import ClientAddressResolver

DEVELOPMENT_ENVIRONMENTS = frozenset({"dev", "local"})


class Settings(BaseSettings):
    """Configuration lue depuis l'environnement (jamais de secret en dur)."""

    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    service_name: str = "basecamp-auth"
    environment: str = "dev"

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "auth"
    db_user: str = "auth"
    db_password: str = ""  # fournie par l'environnement (APP_DB_PASSWORD), jamais versionnee

    log_pseudonym_key: str = (
        ""  # cle HMAC des empreintes d'email dans les logs (APP_LOG_PSEUDONYM_KEY)
    )

    # Jetons de service (WORK-39). Les cles sont montees en secrets Docker, jamais dans l'environnement.
    jwt_private_key_file: str = "/run/secrets/auth_jwt_private_key"
    jwt_public_key_file: str = "/run/secrets/auth_jwt_public_key"
    jwt_issuer: str = "basecamp-auth"
    service_token_rate_limit_per_minute: int = Field(default=60, gt=0)
    # Clients de service a amorcer : {"shop": ["payments:write"]} (JSON, non secret). Les secrets
    # se lisent a part (APP_SERVICE_CLIENT_SECRET_<CLIENT>) par la commande d'amorcage uniquement.
    service_clients: dict[str, list[str]] = Field(default_factory=dict)

    # Envoi d'emails (Mailpit en local, relais SMTP reel ailleurs).
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "comptes@basecamp.local"
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")  # APP_SMTP_PASSWORD, jamais versionne
    smtp_starttls: bool = False
    smtp_timeout_seconds: float = 5.0
    # Origine publique du site : base des liens envoyes par email.
    public_base_url: str = "http://localhost:8080"

    # Jetons d'acces des clients (WORK-34), signes avec la meme cle que les jetons de service.
    # Dossier facultatif de cles publiques PEM precedentes, gardees pendant une rotation.
    jwt_previous_public_keys_dir: str = ""
    jwt_audience: str = "basecamp-client-api"
    access_token_ttl_seconds: int = Field(default=900, gt=0)
    refresh_token_ttl_seconds: int = Field(default=604800, gt=0)

    # Connexion du back-office en trois temps (WORK-59) : routes /backoffice/* montees seulement si
    # `backoffice_enabled`. Il faut alors un verificateur de visage : `fake` (developpement
    # uniquement, aucune reconnaissance reelle) ; aucun adaptateur reel n'est encore branche.
    backoffice_enabled: bool = False
    face_verifier: Literal["none", "fake", "visage-id"] = "none"
    # Seuil de decision du verificateur reel (similarite cosinus). Defaut 0,23 : valeur de la team IA
    # (jeu public LFW, ~0,1 % de faux accepts); a recalibrer avec de vraies photos.
    face_threshold: float = Field(default=0.23, gt=0, lt=1)
    # Cle AES-256 (32 octets en base64) qui chiffre les gabarits faciaux au repos : secret monte,
    # jamais versionne (scripts/init-auth-keys.sh la genere en developpement).
    face_template_key_file: str = "/run/secrets/auth_face_template_key"
    backoffice_challenge_ttl_seconds: int = Field(default=120, gt=0)

    # Adresse reelle du client (WORK-59) : plages CIDR (separees par des virgules) des proxies dont on
    # croit X-Forwarded-For. Vide (defaut) : seule l'adresse du pair TCP est utilisee.
    trusted_proxies: str = ""

    # Verrouillage progressif (WORK-37) : `lockout_max_failures` echecs en `lockout_window_seconds`
    # verrouillent le sujet; les durees (secondes, separees par des virgules) forment l'echelle des
    # recidives et la derniere est le plafond. Oublie apres `lockout_memory_seconds` sans verrou.
    lockout_max_failures: int = Field(default=5, ge=1)
    lockout_window_seconds: int = Field(default=900, gt=0)
    lockout_durations_seconds: str = "900,1800,3600"
    lockout_memory_seconds: int = Field(default=86400, gt=0)

    # Verrouillage PAR ETAPE (WORK-56), sans escalade : `max_failures` echecs en `window_seconds`
    # verrouillent pour `duration_seconds` fixes. Etapes du back-office (mot de passe operateur,
    # visage) et compteur par adresse source (toutes etapes). Les etapes non listees gardent la
    # regle progressive ci-dessus.
    lockout_operator_password_max_failures: int = Field(default=3, ge=1)
    lockout_operator_password_window_seconds: int = Field(default=600, gt=0)
    lockout_operator_password_duration_seconds: int = Field(default=300, gt=0)
    lockout_face_max_failures: int = Field(default=5, ge=1)
    lockout_face_window_seconds: int = Field(default=600, gt=0)
    lockout_face_duration_seconds: int = Field(default=300, gt=0)
    lockout_address_max_failures: int = Field(default=20, ge=1)
    lockout_address_window_seconds: int = Field(default=900, gt=0)
    lockout_address_duration_seconds: int = Field(default=900, gt=0)

    @property
    def lockout_durations(self) -> tuple[int, ...]:
        return tuple(
            int(part) for part in self.lockout_durations_seconds.split(",") if part.strip()
        )

    @model_validator(mode="after")
    def _check_lockout_durations(self) -> "Settings":
        try:
            durations = self.lockout_durations
        except ValueError:
            raise ValueError(
                "APP_LOCKOUT_DURATIONS_SECONDS must be comma-separated integers"
            ) from None
        if not durations or any(value <= 0 for value in durations):
            raise ValueError("APP_LOCKOUT_DURATIONS_SECONDS needs at least one positive duration")
        return self

    @model_validator(mode="after")
    def _check_face_verifier(self) -> "Settings":
        if self.face_verifier == "fake" and self.environment not in DEVELOPMENT_ENVIRONMENTS:
            raise ValueError("APP_FACE_VERIFIER=fake is only allowed in dev and local")
        if self.backoffice_enabled and self.face_verifier == "none":
            raise ValueError("APP_BACKOFFICE_ENABLED needs a real face verifier adapter")
        return self

    @model_validator(mode="after")
    def _check_trusted_proxies(self) -> "Settings":
        try:
            ClientAddressResolver.from_text(self.trusted_proxies)
        except ValueError:
            raise ValueError("APP_TRUSTED_PROXIES must be comma-separated CIDR ranges") from None
        return self

    @model_validator(mode="after")
    def _require_pseudonym_key_outside_development(self) -> "Settings":
        if self.environment not in DEVELOPMENT_ENVIRONMENTS and not self.log_pseudonym_key:
            raise ValueError("APP_LOG_PSEUDONYM_KEY is required outside dev and local")
        return self

    @property
    def database_url(self) -> str:
        url = URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
        return url.render_as_string(hide_password=False)
