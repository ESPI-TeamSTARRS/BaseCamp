from pydantic import BaseModel


class PasswordResetMessageResponse(BaseModel):
    message: str
