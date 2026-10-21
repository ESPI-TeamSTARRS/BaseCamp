from pydantic import BaseModel, ConfigDict, Field

MAX_TOKEN_LENGTH = 256


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=MAX_TOKEN_LENGTH)
