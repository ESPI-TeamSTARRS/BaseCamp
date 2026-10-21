"""Catalogue des evenements metier de la tranche (noms et motifs stables, jamais renommes)."""

LOGIN_SUCCEEDED = "auth.login_succeeded"
LOGIN_FAILED = "auth.login_failed"
TOKEN_REJECTED = "auth.token_rejected"  # noqa: S105
TOKEN_REFRESHED = "auth.token_refreshed"  # noqa: S105
REFRESH_REJECTED = "auth.refresh_rejected"
REFRESH_REUSE_DETECTED = "auth.refresh_reuse_detected"
LOGOUT_COMPLETED = "auth.logout_completed"

REASON_INVALID_CREDENTIALS = "invalid_credentials"
REASON_INVALID_REFRESH_TOKEN = "invalid_refresh_token"  # noqa: S105
REASON_REFRESH_REUSED = "refresh_token_reused"

CAUSE_UNKNOWN_ACCOUNT = "unknown_account"
CAUSE_WRONG_PASSWORD = "wrong_password"  # noqa: S105
CAUSE_ACCOUNT_DISABLED = "account_disabled"
CAUSE_UNKNOWN_TOKEN = "unknown_token"  # noqa: S105
CAUSE_EXPIRED_TOKEN = "expired_token"  # noqa: S105

RESOURCE_ACCOUNT = "account"
RESOURCE_ACCESS_TOKEN = "access_token"  # noqa: S105
RESOURCE_REFRESH_TOKEN = "refresh_token"  # noqa: S105
ACTOR_USER = "user"
