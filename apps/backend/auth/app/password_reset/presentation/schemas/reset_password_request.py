from pydantic import BaseModel, ConfigDict, Field, SecretStr

MAX_TOKEN_LENGTH = 256
MAX_PASSWORD_LENGTH = 256  # garde-fou HTTP : la regle metier (128) est portee par le domaine


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: SecretStr = Field(min_length=1, max_length=MAX_TOKEN_LENGTH)
    password: SecretStr = Field(max_length=MAX_PASSWORD_LENGTH)
