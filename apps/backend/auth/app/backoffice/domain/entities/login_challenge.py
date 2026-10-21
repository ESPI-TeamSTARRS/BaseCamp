from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID


@dataclass(frozen=True)
class LoginChallenge:
    """Defi a usage unique d'une connexion en trois temps (identifiant, visage, mot de passe).

    `digest` est l'empreinte du jeton remis au client (le jeton n'est jamais stocke). `account_id`
    vaut `None` pour un defi LEURRE : identifiant inconnu, compte sans droit ou desactive; il est
    indiscernable d'un vrai defi pour le client, et le visage presente sera refuse comme un visage
    faux. `email_hash` et `address_hash` sont des empreintes opaques (jamais l'adresse ni l'email) :
    elles cle les compteurs de verrouillage et les journaux.
    """

    digest: str
    account_id: UUID | None
    email_hash: str
    address_hash: str
    expires_at: datetime
    face_ok: bool = False

    @classmethod
    def issue(
        cls,
        digest: str,
        account_id: UUID | None,
        email_hash: str,
        address_hash: str,
        now: datetime,
        ttl_seconds: int,
    ) -> "LoginChallenge":
        return cls(
            digest, account_id, email_hash, address_hash, now + timedelta(seconds=ttl_seconds)
        )

    @property
    def decoy(self) -> bool:
        return self.account_id is None

    def expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def with_face_ok(self) -> "LoginChallenge":
        """Le visage est accepte : le defi peut servir une fois a l'etape du mot de passe."""
        return replace(self, face_ok=True)
