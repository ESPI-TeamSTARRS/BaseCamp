import ipaddress
from collections.abc import Iterable

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class ClientAddressResolver:
    """Adresse reelle du client, sans jamais croire un en-tete qu'un client peut poser.

    L'adresse du pair TCP est la seule donnee sure. `X-Forwarded-For` n'est lu que si le pair est un
    proxy de confiance (`APP_TRUSTED_PROXIES`, plages CIDR : reseaux Docker, plages Cloudflare). La
    liste est alors parcourue de la DROITE vers la gauche (chaque proxy de confiance ajoute l'adresse
    qu'il a vue) et la premiere adresse qui n'est pas un proxy de confiance est le client : une
    adresse posee a gauche par le client n'est jamais retenue. `CF-Connecting-IP` n'est pas lu : un
    client qui atteint la passerelle sans passer par Cloudflare pourrait le forger.
    """

    def __init__(self, trusted: Iterable[IPNetwork]) -> None:
        self._trusted = tuple(trusted)

    @classmethod
    def from_cidrs(cls, cidrs: Iterable[str]) -> "ClientAddressResolver":
        try:
            return cls(ipaddress.ip_network(cidr.strip(), strict=False) for cidr in cidrs)
        except ValueError:
            raise ValueError("trusted proxies must be CIDR ranges") from None

    @classmethod
    def from_text(cls, text: str) -> "ClientAddressResolver":
        """Plages separees par des virgules (valeur de `APP_TRUSTED_PROXIES`); vide = aucun proxy."""
        return cls.from_cidrs(part for part in text.split(",") if part.strip())

    def resolve(self, peer: str | None, forwarded_for: str | None) -> str | None:
        if not peer:
            return None
        peer_address = self._parse(peer)
        if peer_address is None or not self._is_trusted(peer_address):
            return peer
        chain = [
            address
            for address in (self._parse(part) for part in (forwarded_for or "").split(","))
            if address is not None
        ]
        if not chain:
            return peer
        for address in reversed(chain):
            if not self._is_trusted(address):
                return str(address)
        return str(chain[0])  # toute la chaine est interne : l'origine est la plus a gauche

    def _is_trusted(self, address: IPAddress) -> bool:
        return any(
            address in network for network in self._trusted if network.version == address.version
        )

    @staticmethod
    def _parse(value: str) -> IPAddress | None:
        try:
            return ipaddress.ip_address(value.strip())
        except ValueError:
            return None
