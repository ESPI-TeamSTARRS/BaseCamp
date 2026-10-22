from pydantic import BaseModel, ConfigDict, Field, SecretStr

MAX_TOKEN_LENGTH = 128
MAX_PASSWORD_LENGTH = 256  # garde-fou HTTP avant tout hachage
MAX_PHOTOS = 10
# 1 Mo par photo une fois decodee = 1 398 104 caracteres en base64 : garde-fou HTTP avant le decodage.
MAX_BASE64_LENGTH = 1_398_104


class InvitationCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: SecretStr = Field(min_length=1, max_length=MAX_TOKEN_LENGTH)
    password: SecretStr = Field(max_length=MAX_PASSWORD_LENGTH)
    images: list[str] = Field(max_length=MAX_PHOTOS)  # 3 a 10 photos JPEG ou PNG en base64

    def model_post_init(self, __context: object) -> None:
        if any(len(image) > MAX_BASE64_LENGTH for image in self.images):
            raise ValueError("photo too large")
