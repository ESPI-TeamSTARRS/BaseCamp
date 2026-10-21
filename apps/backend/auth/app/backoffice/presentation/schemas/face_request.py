from pydantic import BaseModel, ConfigDict, Field

MAX_CHALLENGE_LENGTH = 128
MAX_IMAGES = 3
# 1 Mo par image une fois decodee = 1 398 104 caracteres en base64 : garde-fou HTTP avant tout decodage.
MAX_BASE64_LENGTH = 1_398_104


class FaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: str = Field(min_length=1, max_length=MAX_CHALLENGE_LENGTH)
    images: list[str] = Field(
        min_length=1, max_length=MAX_IMAGES
    )  # JPEG ou PNG en base64, 1 Mo chacune

    def model_post_init(self, __context: object) -> None:
        if any(len(image) > MAX_BASE64_LENGTH for image in self.images):
            raise ValueError("image too large")
