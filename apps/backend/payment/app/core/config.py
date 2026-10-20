from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


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
