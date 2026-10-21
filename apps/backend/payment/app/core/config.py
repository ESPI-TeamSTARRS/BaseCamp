from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

DEVELOPMENT_ENVIRONMENTS = frozenset({"dev", "local"})


class Settings(BaseSettings):
    """Configuration lue depuis l'environnement (jamais de secret en dur)."""

    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    service_name: str = "basecamp-payment"
    environment: str = "dev"

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "payment"
    db_user: str = "payment"
    # Jetons de service statiques par appelant (APP_SERVICE_TOKENS='{"shop": "..."}'), via l'env.
    service_tokens: dict[str, str] = {}
    intent_ttl_minutes: int = 30
    max_amount_cents: int = 500_000  # plafond par intention : 5 000 EUR

    db_password: str = ""  # fournie par l'environnement (APP_DB_PASSWORD), jamais versionnee

    # Pool de connexions borne : taille totale max = pool + debordement, par instance.
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_seconds: float = 3.0  # attente d'une connexion libre avant 503
    db_connect_timeout_seconds: int = 2
    db_statement_timeout_ms: int = 5_000

    # Garde-fous HTTP (par instance).
    max_body_bytes: int = 16_384
    read_timeout_seconds: float = 5.0  # lecture du corps de la requete
    write_timeout_seconds: float = 5.0  # envoi de la reponse
    request_timeout_seconds: float = 10.0  # duree totale d'une requete
    max_concurrent_requests: int = 64  # au-dela : 503 immediat (/health exclu)

    # Limitation de debit par appelant et par route, compteurs partages en base (fenetre fixe).
    rate_limit_window_seconds: int = 60
    rate_limit_create_per_window: int = 60
    rate_limit_read_per_window: int = 120

    log_pseudonym_key: str = (
        ""  # cle HMAC des empreintes d'email dans les logs (APP_LOG_PSEUDONYM_KEY)
    )

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
