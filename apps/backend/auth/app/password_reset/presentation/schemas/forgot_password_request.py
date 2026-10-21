from pydantic import BaseModel, ConfigDict, Field

MAX_EMAIL_LENGTH = 320


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=MAX_EMAIL_LENGTH)
