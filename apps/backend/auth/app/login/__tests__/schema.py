"""Schema des tests d'integration : les vraies migrations (0004, 0007, 0008 puis 0009) sur SQLite en memoire."""

import importlib.util
from datetime import datetime
from pathlib import Path
from types import ModuleType
from uuid import UUID

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool

MIGRATIONS = Path(__file__).resolve().parents[3] / "alembic" / "versions"
CREATED_AT = datetime(2026, 1, 1, 12, 0).isoformat(sep=" ")


def load_migration(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, MIGRATIONS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migrated_engine() -> Engine:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        load_migration("0004_users_et_verification").upgrade()
        load_migration("0007_login").upgrade()
        load_migration("0008_refresh_rotation").upgrade()
        load_migration("0009_login_lockouts").upgrade()
    return engine


def insert_user(
    engine: Engine,
    user_id: UUID,
    email: str,
    password_hash: str,
    role: str = "customer",
    verified: bool = True,
    disabled: bool = False,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash, role, email_verified_at, "
                "disabled_at, created_at) VALUES (:id, :email, :hash, :role, :verified, "
                ":disabled, :created)"
            ),
            {
                "id": user_id.hex,
                "email": email,
                "hash": password_hash,
                "role": role,
                "verified": CREATED_AT if verified else None,
                "disabled": CREATED_AT if disabled else None,
                "created": CREATED_AT,
            },
        )
