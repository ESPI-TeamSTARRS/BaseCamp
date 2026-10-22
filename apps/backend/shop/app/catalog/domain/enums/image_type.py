from enum import Enum


class ImageType(Enum):
    """Formats d'image acceptés : extension et type de contenu servis par le bucket."""

    JPEG = ("jpg", "image/jpeg")
    PNG = ("png", "image/png")
    WEBP = ("webp", "image/webp")

    @property
    def extension(self) -> str:
        return str(self.value[0])

    @property
    def content_type(self) -> str:
        return str(self.value[1])
