from pydantic import BaseModel, ConfigDict, Field, SecretStr

MAX_EMAIL_LENGTH = 320
MAX_PASSWORD_LENGTH = 256  # garde-fou HTTP contre un corps demesure avant tout hachage


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    password: SecretStr = Field(max_length=MAX_PASSWORD_LENGTH)
