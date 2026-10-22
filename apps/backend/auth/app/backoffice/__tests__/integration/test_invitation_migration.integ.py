from sqlalchemy import inspect

from app.backoffice.__tests__.stack import BackofficeStack
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.login.__tests__.stack import LoginStack  # noqa: F401


def test_the_migration_adds_the_invitation_table_with_only_the_digest_of_the_token() -> None:
    stack = BackofficeStack(InMemoryBusinessEventLogger())
    try:
        inspector = inspect(stack.engine)

        columns = {column["name"] for column in inspector.get_columns("operator_invitations")}
        indexes = {index["name"] for index in inspector.get_indexes("operator_invitations")}

        assert columns == {
            "digest",
            "email",
            "created_at",
            "expires_at",
            "consumed_at",
            "revoked_at",
        }
        assert {"ix_operator_invitations_email", "ix_operator_invitations_expires_at"} <= indexes
        assert "token" not in columns
    finally:
        stack.engine.dispose()
