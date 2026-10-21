from typing import Literal

from pydantic import BaseModel, ConfigDict


class ConfirmPaymentRequest(BaseModel):
    """Aucune donnée bancaire : seule une méthode de test connue est acceptée."""

    model_config = ConfigDict(extra="forbid")

    payment_method: Literal["pm_test_success", "pm_test_declined", "pm_test_timeout"]
