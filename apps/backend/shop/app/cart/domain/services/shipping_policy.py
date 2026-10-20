class ShippingPolicy:
    """Regle de livraison : 5,90 EUR sous 80 EUR de sous-total, gratuite a partir de 80 EUR."""

    FREE_SHIPPING_THRESHOLD_CENTS = 8000
    STANDARD_SHIPPING_CENTS = 590

    @classmethod
    def shipping_cents(cls, subtotal_cents: int) -> int:
        if subtotal_cents == 0 or subtotal_cents >= cls.FREE_SHIPPING_THRESHOLD_CENTS:
            return 0
        return cls.STANDARD_SHIPPING_CENTS

    @classmethod
    def amount_remaining_cents(cls, subtotal_cents: int) -> int:
        return max(0, cls.FREE_SHIPPING_THRESHOLD_CENTS - subtotal_cents)
