from pydantic import BaseModel, ConfigDict, Field

MAX_EMAIL_LENGTH = 320


class IdentifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=MAX_EMAIL_LENGTH)
