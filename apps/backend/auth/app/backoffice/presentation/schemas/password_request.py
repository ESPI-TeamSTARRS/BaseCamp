from pydantic import BaseModel, ConfigDict, Field, SecretStr

MAX_CHALLENGE_LENGTH = 128
MAX_PASSWORD_LENGTH = 256  # garde-fou HTTP contre un corps demesure avant tout hachage


class PasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: str = Field(min_length=1, max_length=MAX_CHALLENGE_LENGTH)
    password: SecretStr = Field(max_length=MAX_PASSWORD_LENGTH)
