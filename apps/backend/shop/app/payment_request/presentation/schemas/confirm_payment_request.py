from typing import Literal

from pydantic import BaseModel, ConfigDict


class ConfirmPaymentRequest(BaseModel):
    """Seule une méthode de test est acceptée : aucun numéro de carte n'existe dans ce contrat."""

    model_config = ConfigDict(extra="forbid")

    payment_method: Literal["pm_test_success", "pm_test_declined"]
