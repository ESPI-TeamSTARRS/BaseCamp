from enum import StrEnum


class SubjectType(StrEnum):
    """Ce qui est verrouille : un compte (empreinte de l'identifiant) ou une adresse source.

    Les deux ont leurs propres compteurs et seuils : un tiers qui connait l'adresse d'un compte ne
    peut pas le verrouiller depuis sa propre adresse sans etre bloque lui-meme d'abord.
    """

    ACCOUNT = "account"
    SOURCE_ADDRESS = "address"
