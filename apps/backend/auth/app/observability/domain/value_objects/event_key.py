from dataclasses import dataclass


@dataclass(frozen=True)
class EventKey:
    """Cle d'une serie d'evenements metier : nom, resultat, motif (codes fermes) et un detail borne.

    `detail` est soit un code ferme (cause d'un echec, etape verrouillee), soit le nom d'un client de
    service CONNU (jamais une valeur saisie par l'appelant : un client inconnu devient `unknown`).
    """

    event: str
    outcome: str
    reason: str
    detail: str
