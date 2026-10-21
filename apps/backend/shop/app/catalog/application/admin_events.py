from collections.abc import Mapping

from app.catalog.domain.entities.product import Product
from app.core.events.business_event import BusinessEvent, Scalar

CATALOG_ADMIN_CHANGE = "catalog_admin.change"

CREATE = "create"
UPDATE = "update"
ARCHIVE = "archive"
IMAGE = "image"


def change(
    action: str,
    actor_hash: str,
    product: Product,
    old_price_cents: int | None,
) -> BusinessEvent:
    """Un changement du catalogue par un opérateur : acteur pseudonymisé, produit, prix et stock.

    Jamais de description ni de donnée personnelle : seulement des identifiants et des chiffres.
    """
    attributes: Mapping[str, Scalar] = {
        "action": action,
        "old_price_cents": old_price_cents,
        "new_price_cents": product.price_cents,
        "new_stock": product.stock,
        "version": product.version,
    }
    return BusinessEvent.success(
        CATALOG_ADMIN_CHANGE,
        actor_type="user",
        actor_id=actor_hash,
        resource_type="product",
        resource_id=product.id,
        attributes=attributes,
    )
