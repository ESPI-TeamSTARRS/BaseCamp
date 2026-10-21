from dataclasses import dataclass

from app.caller_identity.domain.entities.caller import Caller
from app.caller_identity.domain.enums.token_kind import TokenKind


@dataclass(frozen=True)
class CallerRequirement:
    """Ce qu'une route exige de son appelant.

    - `scope` : un jeton de SERVICE doit porter ce scope;
    - `operator_role` : un jeton CLIENT est accepte s'il porte ce role (None = jetons client refuses).
    Un jeton qui ne satisfait aucune des deux branches est refuse (403 s'il est authentique).
    """

    scope: str
    operator_role: str | None = None

    def accepts(self, caller: Caller) -> bool:
        if caller.kind is TokenKind.SERVICE:
            return self.scope in caller.scopes
        return self.operator_role is not None and self.operator_role in caller.roles

    @property
    def accepts_clients(self) -> bool:
        return self.operator_role is not None
