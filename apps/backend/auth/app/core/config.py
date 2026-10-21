from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

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
