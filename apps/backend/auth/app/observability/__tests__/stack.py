"""Service complet (cablage reel, SQLite en memoire, journal capture) pour les tests d'observabilite."""

import importlib.util
import io
import json
from pathlib import Path
from types import ModuleType
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.main import create_app
from app.registration.infrastructure.clients.argon2_password_hasher import Argon2PasswordHasher
from app.service_token.domain.entities.service_client import ServiceClient
from app.service_token.domain.enums.service_scope import ServiceScope
from app.service_token.infrastructure.hashers.argon2_secret_hasher import Argon2SecretHasher
from app.service_token.infrastructure.repositories.sqlalchemy_service_client_repository import (
    SqlAlchemyServiceClientRepository,
)

MIGRATIONS = Path(__file__).resolve().parents[3] / "alembic" / "versions"
SCHEMA = Path(__file__).resolve().parents[6] / "docs/development/log-event.schema.json"
VALIDATOR = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
CORRELATION = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
SHOP_SECRET = "secret-du-client-shop-0001"
OWNER_EMAIL = "camille.privee@example.test"
OWNER_PHRASE = "Bivouac-au-sommet-2026"
MIGRATION_ORDER = (
    "0001_initial",
    "0003_clients_de_service",
    "0004_users_et_verification",
    "0006_reinitialisation_mot_de_passe",
    "0007_login",
    "0008_refresh_rotation",
    "0009_login_lockouts",
)


def load_migration(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, MIGRATIONS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_keys(directory: Path) -> tuple[str, str]:
    key = Ed25519PrivateKey.generate()
    private = directory / "private.pem"
    public = directory / "public.pem"
    private.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    public.write_bytes(
        key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )
    return str(private), str(public)


class ObservedService:
    """Application reelle : les lignes de journal sortent sur la sortie standard, capturees."""

    def __init__(self, tmp_path: Path) -> None:
        self._stream = io.StringIO()
        private, public = write_keys(tmp_path)
        self.engine: Engine = create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        with (
            self.engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
        ):
            for name in MIGRATION_ORDER:
                load_migration(name).upgrade()
        settings = Settings(
            jwt_private_key_file=private,
            jwt_public_key_file=public,
            service_clients={"shop": ["payments:write"]},
            environment="dev",
        )
        self.application: FastAPI = create_app(settings, self.engine, self._stream)
        hasher = Argon2SecretHasher()
        SqlAlchemyServiceClientRepository(self.engine).save(
            ServiceClient(
                "shop", frozenset({ServiceScope.PAYMENTS_WRITE}), hasher.hash(SHOP_SECRET)
            )
        )
        self._insert_user(OWNER_EMAIL, OWNER_PHRASE)

    def _insert_user(self, email: str, password: str) -> None:
        from uuid import uuid4

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, role, email_verified_at, "
                    "created_at) VALUES (:id, :email, :hash, 'customer', '2026-01-01 12:00:00', "
                    "'2026-01-01 12:00:00')"
                ),
                {"id": uuid4().hex, "email": email, "hash": Argon2PasswordHasher().hash(password)},
            )

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=self.application), base_url="http://test")

    def all_output(self) -> str:
        """Tout ce que le journal a ecrit depuis le debut du test."""
        return self._stream.getvalue()

    def lines(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.all_output().splitlines() if line.startswith("{")]


def metric(text_body: str, series: str) -> float:
    """Valeur d'un echantillon exact (nom et libelles), 0.0 s'il est absent."""
    for line in text_body.splitlines():
        if line.startswith(series + " "):
            return float(line.rsplit(" ", 1)[1])
    return 0.0
