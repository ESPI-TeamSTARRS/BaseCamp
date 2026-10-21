import ipaddress

IPV4_PREFIX = 24
IPV6_PREFIX = 48


def truncate_address(address: str | None) -> str | None:
    """Reseau de l'adresse (/24 en IPv4, /48 en IPv6) : assez pour reperer une source, jamais l'hote.

    Une adresse absente ou illisible donne `None` : on ne journalise rien plutot qu'une valeur
    douteuse.
    """
    if not address or not address.strip():
        return None
    try:
        parsed = ipaddress.ip_address(address.strip())
    except ValueError:
        return None
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    prefix = IPV4_PREFIX if parsed.version == 4 else IPV6_PREFIX
    return str(ipaddress.ip_network(f"{parsed}/{prefix}", strict=False))
