from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class CreatePaymentIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_reference: Annotated[
        str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    ]
    amount: Annotated[StrictInt, Field(gt=0)]
    currency: Literal["EUR"]
