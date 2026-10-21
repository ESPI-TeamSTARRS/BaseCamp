from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

DEVELOPMENT_ENVIRONMENTS = frozenset({"dev", "local"})


class Settings(BaseSettings):
    """Configuration lue depuis l'environnement (jamais de secret en dur)."""

    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    service_name: str = "basecamp-shop"
    environment: str = "dev"

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "shop"
    db_user: str = "shop"
    db_password: str = ""  # fournie par l'environnement (APP_DB_PASSWORD), jamais versionnee

    # Appels a payment : delais courts pour qu'un payment arrete ou lent ne bloque jamais la boutique.
    # `http` : service payment (par défaut) ; `simulated` : fournisseur simulé en base, sans réseau ni clé.
    payment_provider: Literal["http", "simulated"] = "http"
    payment_url: str = "http://payment:8000"
    # Jeton de service de shop aupres de payment : emis par `auth` (`POST /internal/token`) a partir
    # des identifiants du client `shop`; le secret vient de l'environnement (APP_AUTH_CLIENT_SECRET).
    auth_issue_url: str = "http://auth:8000/internal/token"
    auth_client_id: str = "shop"
    auth_client_secret: str = ""
    payment_audience: str = "payment"
    payment_scope: str = "payments:write"
    payment_renew_margin_seconds: float = 30.0
    payment_connect_timeout_seconds: float = 1.0
    payment_read_timeout_seconds: float = 3.0

    # Webhook signé de `payment` (WORK-13) : secrets partagés via l'environnement (jamais versionnés).
    # Sans secret, tout webhook est refusé; `previous` sert à la rotation (les deux sont acceptés).
    payment_webhook_secret: str = ""
    payment_webhook_secret_previous: str = ""
    payment_webhook_tolerance_seconds: int = 300

    # Email de confirmation : Mailpit en développement (aucun relais externe).
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_from: str = "commandes@basecamp.local"
    smtp_timeout_seconds: float = 3.0

    # Identification des clients connectes (WORK-40) : jetons d'acces signes par `auth`, verifies
    # localement avec ses cles publiques (JWKS) lues sur le reseau interne `app`.
    auth_jwks_url: str = "http://auth:8000/.well-known/jwks.json"
    auth_profile_url: str = (
        "http://auth:8000/me"  # profil du porteur du jeton (email, verification)
    )
    auth_issuer: str = "basecamp-auth"
    auth_audience: str = "basecamp-client-api"
    auth_jwks_ttl_seconds: float = 300.0
    auth_jwks_min_refetch_seconds: float = 10.0
    auth_connect_timeout_seconds: float = 1.0
    auth_read_timeout_seconds: float = 2.0

    # Délai avant qu'une commande impayée expire et rende son stock (minutes).
    order_expiration_minutes: int = 30

    media_base_url: str = "/media"  # prefixe public des images (servies par la passerelle)

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
