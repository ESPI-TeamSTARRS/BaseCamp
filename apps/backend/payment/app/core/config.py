from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

DEVELOPMENT_ENVIRONMENTS = frozenset({"dev", "local"})
MIN_WEBHOOK_SECRET_LENGTH = 32


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
    # Expiration des intentions non confirmées : nombre d'intentions traitées par transaction.
    expiration_batch_size: int = Field(default=100, gt=0, le=1000)
    # Délai simulé du fournisseur interne pour pm_test_timeout : toujours borné (10 s au plus).
    provider_timeout_seconds: float = Field(default=2.0, gt=0, le=10)

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

    # Fenêtre de contrôle du grand livre pour /metrics (intentions créées dans les N dernières heures).
    metrics_ledger_lookback_hours: int = Field(default=24, ge=1, le=720)

    log_pseudonym_key: str = (
        ""  # cle HMAC des empreintes d'email dans les logs (APP_LOG_PSEUDONYM_KEY)
    )

    # Webhook sortant vers la boutique (worker `python -m app.webhook.presentation.worker_main`).
    # Secrets fournis par l'environnement seulement. Rotation : APP_WEBHOOK_SECRET (courant) et
    # APP_WEBHOOK_SECRET_PREVIOUS (ancien) signent ensemble le temps que la boutique bascule.
    webhook_url: str = ""
    webhook_secret: SecretStr = SecretStr("")
    webhook_secret_previous: SecretStr = SecretStr("")
    webhook_max_attempts: int = Field(default=6, ge=1, le=20)
    webhook_backoff_base_seconds: float = Field(default=5.0, gt=0, le=3600)
    webhook_backoff_max_seconds: float = Field(default=300.0, gt=0, le=86_400)
    webhook_timeout_seconds: float = Field(default=3.0, gt=0, le=10)
    webhook_poll_interval_seconds: float = Field(default=1.0, gt=0, le=60)

    @model_validator(mode="after")
    def _validate_webhook(self) -> "Settings":
        if self.webhook_url and not self.webhook_url.startswith(("http://", "https://")):
            raise ValueError("APP_WEBHOOK_URL must be an http(s) URL")
        if (
            self.webhook_secret_previous.get_secret_value()
            and not self.webhook_secret.get_secret_value()
        ):
            raise ValueError("APP_WEBHOOK_SECRET_PREVIOUS requires APP_WEBHOOK_SECRET")
        if any(len(secret) < MIN_WEBHOOK_SECRET_LENGTH for secret in self.webhook_secrets):
            raise ValueError("webhook secrets must be at least 32 characters")
        if self.webhook_backoff_base_seconds > self.webhook_backoff_max_seconds:
            raise ValueError("APP_WEBHOOK_BACKOFF_BASE_SECONDS exceeds the maximum")
        return self

    @property
    def webhook_secrets(self) -> list[str]:
        """Secrets de signature, le courant d'abord, sans valeur vide."""
        candidates = (self.webhook_secret, self.webhook_secret_previous)
        return [value for secret in candidates if (value := secret.get_secret_value())]

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
