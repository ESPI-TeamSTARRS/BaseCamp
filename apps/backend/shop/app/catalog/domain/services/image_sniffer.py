from app.catalog.domain.enums.image_type import ImageType

_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"
_RIFF = b"RIFF"
_WEBP = b"WEBP"
_WEBP_HEADER = 12


def sniff_image_type(content: bytes) -> ImageType | None:
    """Type réel d'après les premiers octets (jamais l'extension ni l'en-tête annoncés par le client)."""
    if content.startswith(_JPEG):
        return ImageType.JPEG
    if content.startswith(_PNG):
        return ImageType.PNG
    if len(content) >= _WEBP_HEADER and content[:4] == _RIFF and content[8:12] == _WEBP:
        return ImageType.WEBP
    return None
