from abc import ABC, abstractmethod


class GuestOrderLinker(ABC):
    @abstractmethod
    def link(self, user_id: str, email: str) -> int:
        """Rattache au compte les commandes invitees (sans compte) passees avec cet email.

        Insensible a la casse, ne touche jamais une commande deja rattachee; renvoie leur nombre.
        """
