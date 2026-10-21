from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy.engine.default import DefaultDialect

from app.registration.infrastructure.models.utc_date_time import UtcDateTime

DIALECT = DefaultDialect()


class TestUtcDateTime:
    def test_bound_values_are_converted_to_utc(self) -> None:
        paris = timezone(timedelta(hours=1))

        bound = UtcDateTime().process_bind_param(datetime(2026, 1, 1, 13, tzinfo=paris), DIALECT)

        assert bound == datetime(2026, 1, 1, 12, tzinfo=UTC)
        assert bound is not None
        assert bound.utcoffset() == timedelta(0)

    def test_naive_values_read_back_are_flagged_utc(self) -> None:
        result = UtcDateTime().process_result_value(datetime(2026, 1, 1, 12), DIALECT)

        assert result == datetime(2026, 1, 1, 12, tzinfo=UTC)

    def test_aware_values_read_back_are_normalized_to_utc(self) -> None:
        paris = timezone(timedelta(hours=1))

        result = UtcDateTime().process_result_value(datetime(2026, 1, 1, 13, tzinfo=paris), DIALECT)

        assert result == datetime(2026, 1, 1, 12, tzinfo=UTC)

    def test_none_stays_none(self) -> None:
        assert UtcDateTime().process_bind_param(None, DIALECT) is None
        assert UtcDateTime().process_result_value(None, DIALECT) is None
