from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt

_BIGINT_MAX = 9_223_372_036_854_775_807


class RefundRequest(BaseModel):
    """Seul le montant se déclare : entier de centimes strictement positif, jamais un flottant."""

    model_config = ConfigDict(extra="forbid")

    amount: Annotated[StrictInt, Field(gt=0, le=_BIGINT_MAX)]
