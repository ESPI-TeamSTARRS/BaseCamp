"""Journal d'audit de l'administration (noms et motifs stables, jamais renommes).

Chaque action produit une ligne : qui (acteur), quoi (evenement), cible (`resource_id`), quand
(horodatage de la ligne de journal). Jamais d'adresse en clair ni de mot de passe.
"""

ACCOUNTS_LISTED = "auth.accounts_listed"
ACCOUNT_DISABLED = "auth.account_disabled"
ACCOUNT_ENABLED = "auth.account_enabled"
ADMIN_ACTION_REFUSED = "auth.admin_action_refused"
OPERATOR_CREATED = "auth.operator_created"

REASON_SELF_DISABLE = "cannot_disable_self"
REASON_LAST_OPERATOR = "cannot_disable_last_operator"
REASON_NOT_FOUND = "account_not_found"
REASON_ALREADY_EXISTS = "operator_exists"
REASON_WEAK_PASSWORD = "weak_password"  # noqa: S105

RESOURCE_ACCOUNT = "account"
ACTOR_OPERATOR = "operator"
ACTOR_CLI = "cli"
