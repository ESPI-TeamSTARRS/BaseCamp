from app.intent.domain.enums.currency import Currency
from app.intent.domain.value_objects.request_fingerprint import RequestFingerprint


class TestRequestFingerprint:
    def test_same_request_gives_same_fingerprint(self) -> None:
        first = RequestFingerprint.of("CMD-1", 1000, Currency.EUR)

        assert first == RequestFingerprint.of("CMD-1", 1000, Currency.EUR)

    def test_any_changed_field_changes_the_fingerprint(self) -> None:
        base = RequestFingerprint.of("CMD-1", 1000, Currency.EUR)

        assert RequestFingerprint.of("CMD-2", 1000, Currency.EUR) != base
        assert RequestFingerprint.of("CMD-1", 1001, Currency.EUR) != base

    def test_fields_cannot_be_shifted_between_each_other(self) -> None:
        shifted = RequestFingerprint.of("A|1", 2, Currency.EUR)

        assert shifted != RequestFingerprint.of("A", 12, Currency.EUR)
