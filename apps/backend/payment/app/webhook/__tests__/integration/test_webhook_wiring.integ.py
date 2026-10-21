from pydantic import SecretStr
from sqlalchemy import StaticPool, create_engine

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.config import Settings
from app.webhook.application.deliver_next_event import DeliverNextEventUseCase
from app.webhook.application.requeue_dead_events import RequeueDeadEventsUseCase
from app.webhook.wiring import build_deliver_use_case, build_requeue_use_case

SECRET = "whsec_wiring_0123456789abcdef0123456789abcdef"


class TestWiring:
    def test_the_delivery_use_case_is_built_from_the_environment_settings(self) -> None:
        engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)
        settings = Settings(
            webhook_url="http://shop:8000/webhooks/payment",
            webhook_secret=SecretStr(SECRET),
            webhook_max_attempts=4,
        )

        use_case = build_deliver_use_case(engine, settings, InMemoryBusinessEventLogger())

        assert isinstance(use_case, DeliverNextEventUseCase)

    def test_the_requeue_use_case_needs_neither_url_nor_secret(self) -> None:
        engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)

        use_case = build_requeue_use_case(engine, InMemoryBusinessEventLogger())

        assert isinstance(use_case, RequeueDeadEventsUseCase)
