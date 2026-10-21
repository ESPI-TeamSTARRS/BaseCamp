import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.cart.application.quote_cart import MAX_LINES, MAX_QUANTITY, MIN_QUANTITY
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.order.application.idempotency_key_reused_error import IdempotencyKeyReusedError
from app.order.application.insufficient_stock_error import InsufficientStockError
from app.order.application.invalid_order_error import InvalidOrderError
from app.order.application.place_order_command import PlaceOrderCommand
from app.order.application.placed_order import PlacedOrder
from app.order.domain.entities.order import Order
from app.order.domain.entities.order_line import OrderLine
from app.order.domain.entities.stock_item import StockItem
from app.order.domain.enums.order_status import OrderStatus
from app.order.domain.enums.shipping_country import ShippingCountry
from app.order.domain.errors.duplicate_idempotency_key_error import DuplicateIdempotencyKeyError
from app.order.domain.interfaces.email_pseudonymizer import EmailPseudonymizer
from app.order.domain.interfaces.order_unit_of_work import OrderUnitOfWork
from app.order.domain.services.order_number_generator import OrderNumberGenerator
from app.order.domain.value_objects.shipping_address import ShippingAddress

COUNTRY_MESSAGE = "Pays de livraison non pris en charge."


class PlaceOrderUseCase:
    """Cree une commande en attente de paiement : prix figes, stock reserve, rejeu idempotent."""

    def __init__(
        self,
        uow_factory: Callable[[], OrderUnitOfWork],
        events: BusinessEventLogger,
        pseudonymizer: EmailPseudonymizer,
    ) -> None:
        self._uow_factory = uow_factory
        self._events = events
        self._pseudonymizer = pseudonymizer

    def execute(self, command: PlaceOrderCommand) -> PlacedOrder:
        address = self._validate(command)
        try:
            return self._place(command, address)
        except DuplicateIdempotencyKeyError:
            return self._replay_after_race(command)

    def _place(self, command: PlaceOrderCommand, address: ShippingAddress) -> PlacedOrder:
        with self._uow_factory() as uow:
            found = self._lock_items(uow, command)
            # Relu apres le verrou : une commande validee entre-temps par la meme cle est un rejeu.
            existing = uow.orders.find_by_idempotency_key(command.idempotency_key)
            if existing is not None:
                return self._replayed(existing, command)
            items = self._check_stock(command, found)
            order = self._build_order(command, address, items)
            uow.orders.add(order)
            for line in order.lines:
                uow.stock.reserve(order.id, line.product_id, line.quantity)
            uow.commit()
        self._emit_created(order, command)
        return PlacedOrder(order, created=True)

    def _replay_after_race(self, command: PlaceOrderCommand) -> PlacedOrder:
        with self._uow_factory() as uow:
            existing = uow.orders.find_by_idempotency_key(command.idempotency_key)
        if existing is None:  # pragma: no cover - la cle est unique, l'autre commande existe
            raise InvalidOrderError("Commande introuvable pour cette cle.", "idempotency_lost")
        return self._replayed(existing, command)

    def _replayed(self, existing: Order, command: PlaceOrderCommand) -> PlacedOrder:
        if existing.request_fingerprint != command.fingerprint:
            self._reject(command, "idempotency_key_reused")
            raise IdempotencyKeyReusedError
        self._events.log(
            BusinessEvent.success(
                "order.replayed",
                resource_type="order",
                resource_id=existing.number,
                attributes=self._attributes(command, existing),
            )
        )
        return PlacedOrder(existing, created=False)

    def _lock_items(self, uow: OrderUnitOfWork, command: PlaceOrderCommand) -> dict[str, StockItem]:
        ids = sorted(
            product_id for product_id, _ in command.items
        )  # ordre stable : pas d'interblocage
        found = {item.product_id: item for item in uow.stock.lock_items(ids)}
        if len(found) != len(command.items):
            self._reject(command, "product_not_found")
            raise InvalidOrderError(
                "Un ou plusieurs produits sont introuvables.", "product_not_found"
            )
        return found

    def _check_stock(
        self, command: PlaceOrderCommand, found: dict[str, StockItem]
    ) -> dict[str, StockItem]:
        for product_id, quantity in command.items:
            if found[product_id].stock < quantity:
                self._emit_insufficient(command, product_id)
                raise InsufficientStockError
        return found

    def _build_order(
        self, command: PlaceOrderCommand, address: ShippingAddress, items: dict[str, StockItem]
    ) -> Order:
        lines = tuple(
            OrderLine(product_id, items[product_id].name, items[product_id].price_cents, quantity)
            for product_id, quantity in command.items
        )
        return Order(
            id=str(uuid.uuid4()),
            number=OrderNumberGenerator.generate(),
            status=OrderStatus.PENDING_PAYMENT,
            email=command.email.strip(),
            address=address,
            lines=lines,
            idempotency_key=command.idempotency_key,
            request_fingerprint=command.fingerprint,
            created_at=datetime.now(UTC),
        )

    def _validate(self, command: PlaceOrderCommand) -> ShippingAddress:
        self._validate_items(command)
        country = ShippingCountry.parse(command.country)
        if country is None:
            self._reject(command, "country_not_supported")
            raise InvalidOrderError(COUNTRY_MESSAGE, "country_not_supported")
        return ShippingAddress(
            full_name=command.full_name.strip(),
            line1=command.address_line1.strip(),
            line2=command.address_line2.strip() if command.address_line2 else None,
            postal_code=command.postal_code.strip(),
            city=command.city.strip(),
            country=country,
        )

    def _validate_items(self, command: PlaceOrderCommand) -> None:
        items = command.items
        if not 1 <= len(items) <= MAX_LINES:
            self._reject_invalid(
                command, "Le panier doit contenir entre 1 et 50 lignes.", "invalid_cart"
            )
        if any(not MIN_QUANTITY <= quantity <= MAX_QUANTITY for _, quantity in items):
            self._reject_invalid(
                command,
                "Chaque quantite doit etre comprise entre 1 et 10.",
                "quantity_out_of_range",
            )
        if len({product_id for product_id, _ in items}) != len(items):
            self._reject_invalid(
                command, "Un produit ne peut figurer qu'une seule fois.", "duplicate_product"
            )

    def _reject_invalid(self, command: PlaceOrderCommand, message: str, reason: str) -> None:
        self._reject(command, reason)
        raise InvalidOrderError(message, reason)

    def _reject(self, command: PlaceOrderCommand, reason: str) -> None:
        self._events.log(
            BusinessEvent.denied(
                "order.rejected",
                reason,
                attributes={"email_hash": self._pseudonymizer.pseudonymize(command.email)},
            )
        )

    def _emit_insufficient(self, command: PlaceOrderCommand, product_id: str) -> None:
        self._events.log(
            BusinessEvent.denied(
                "stock.insufficient",
                "insufficient_stock",
                resource_type="product",
                resource_id=product_id,
                attributes={"email_hash": self._pseudonymizer.pseudonymize(command.email)},
            )
        )

    def _emit_created(self, order: Order, command: PlaceOrderCommand) -> None:
        attributes = self._attributes(command, order)
        for name in ("stock.reserved", "order.created"):
            self._events.log(
                BusinessEvent.success(
                    name, resource_type="order", resource_id=order.number, attributes=attributes
                )
            )

    def _attributes(self, command: PlaceOrderCommand, order: Order) -> dict[str, str | int | bool]:
        return {
            "email_hash": self._pseudonymizer.pseudonymize(command.email),
            "line_count": len(order.lines),
            "total_cents": order.total_cents,
            "country": order.address.country.value,
        }
