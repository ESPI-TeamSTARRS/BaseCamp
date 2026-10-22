from app.backoffice.domain.exceptions.image_invalide import ImageInvalide

MIN_IMAGES = 1
MAX_IMAGES = 3
MAX_IMAGE_BYTES = 1_048_576  # 1 Mo par image
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def validate_face_images(images: list[bytes]) -> tuple[bytes, ...]:
    """1 a 3 images JPEG ou PNG de 1 Mo au plus : sinon `ImageInvalide` (le format est controle par
    la signature des octets, jamais par ce que declare le client)."""
    if not MIN_IMAGES <= len(images) <= MAX_IMAGES:
        raise ImageInvalide
    for image in images:
        if not image or len(image) > MAX_IMAGE_BYTES:
            raise ImageInvalide
        if not (image.startswith(JPEG_MAGIC) or image.startswith(PNG_MAGIC)):
            raise ImageInvalide
    return tuple(images)
