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
    payment_service_token: str = ""  # jeton de service de shop aupres de payment, via l'env
    payment_connect_timeout_seconds: float = 1.0
    payment_read_timeout_seconds: float = 3.0

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
