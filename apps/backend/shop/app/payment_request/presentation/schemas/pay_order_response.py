from pydantic import BaseModel


class PayOrderResponse(BaseModel):
    """Ce qu'il faut au front pour confirmer : l'intention, le montant et les méthodes de test."""

    payment_intent_id: str
    status: str
    amount_cents: int
    currency: str
    order_number: str
    payment_methods: list[str]
