"""Catalogue des evenements metier de la tranche (noms et motifs stables, jamais renommes)."""

LOGIN_SUCCEEDED = "auth.login_succeeded"
LOGIN_FAILED = "auth.login_failed"
TOKEN_REJECTED = "auth.token_rejected"  # noqa: S105

REASON_INVALID_CREDENTIALS = "invalid_credentials"

CAUSE_UNKNOWN_ACCOUNT = "unknown_account"
CAUSE_WRONG_PASSWORD = "wrong_password"  # noqa: S105
CAUSE_ACCOUNT_DISABLED = "account_disabled"

RESOURCE_ACCOUNT = "account"
RESOURCE_ACCESS_TOKEN = "access_token"  # noqa: S105
ACTOR_USER = "user"
