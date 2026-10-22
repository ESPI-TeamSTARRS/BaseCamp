from app.backoffice.domain.exceptions.image_invalide import ImageInvalide

MIN_IMAGES = 1
MAX_IMAGES = 3
MAX_IMAGE_BYTES = 1_048_576  # 1 Mo par image
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


MIN_ENROLLMENT_PHOTOS = 3
MAX_ENROLLMENT_PHOTOS = 10


def validate_face_images(images: list[bytes]) -> tuple[bytes, ...]:
    """1 a 3 images JPEG ou PNG de 1 Mo au plus : sinon `ImageInvalide` (le format est controle par
    la signature des octets, jamais par ce que declare le client)."""
    return validate_images(images, MIN_IMAGES, MAX_IMAGES)


def validate_enrollment_photos(photos: list[bytes]) -> tuple[bytes, ...]:
    """3 a 10 photos d'enrolement, memes limites de format et de taille."""
    return validate_images(photos, MIN_ENROLLMENT_PHOTOS, MAX_ENROLLMENT_PHOTOS)


def validate_images(images: list[bytes], minimum: int, maximum: int) -> tuple[bytes, ...]:
    if not minimum <= len(images) <= maximum:
        raise ImageInvalide
    for image in images:
        if not image or len(image) > MAX_IMAGE_BYTES:
            raise ImageInvalide
        if not (image.startswith(JPEG_MAGIC) or image.startswith(PNG_MAGIC)):
            raise ImageInvalide
    return tuple(images)
