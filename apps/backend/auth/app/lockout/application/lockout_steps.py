"""Noms des etapes verrouillables du back-office (la connexion en trois temps les consomme).

L'etape `password` du login client existe deja (`login_events.STEP_PASSWORD`) et garde sa regle
progressive : le mot de passe d'un operateur a sa propre etape, donc sa propre regle et son propre
compteur, sans toucher au login client.
"""

STEP_OPERATOR_PASSWORD = "operator_password"  # noqa: S105 - nom d'etape, pas un secret
STEP_FACE = "face"
STEP_INVITATION = "invitation"  # completion d'une invitation d'operateur (par adresse)
