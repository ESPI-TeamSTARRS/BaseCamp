import hashlib
import hmac

import pytest

from app.webhook.domain.services.webhook_signer import WebhookSigner

SECRET = "whsec_test_secret_for_unit_tests_only"
OLD_SECRET = "whsec_old_secret_for_unit_tests_only"
BODY = '{"id":"evt-1","type":"payment.succeeded"}'
NOW = 1_790_000_000


def _expected(secret: str, timestamp: int, body: str) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()


class TestHeader:
    def test_the_header_carries_the_timestamp_and_the_hmac_sha256_of_t_dot_body(self) -> None:
        header = WebhookSigner([SECRET]).header(NOW, BODY)

        assert header == f"t={NOW},v1={_expected(SECRET, NOW, BODY)}"

    def test_a_known_vector_stays_stable(self) -> None:
        header = WebhookSigner(["secret-de-test-0123456789"]).header(1_700_000_000, '{"a":1}')

        assert header == (
            "t=1700000000,v1=" + _expected("secret-de-test-0123456789", 1_700_000_000, '{"a":1}')
        )
        assert len(header.split("v1=")[1]) == 64

    def test_the_vector_published_in_the_service_doc_stays_stable(self) -> None:
        body = (
            '{"id":"0b6d4e0e-6a3f-4c58-9d8e-5f0f4d1d9a11","type":"payment.succeeded",'
            '"created_at":"2026-10-21T09:00:00.123Z","data":{"payment_intent_id":'
            '"7d2f3c1e-8a41-4d3b-9c55-2a6e0f9b1c42","order_reference":"CMD-2026-0001",'
            '"amount":4990,"currency":"EUR","status":"succeeded"}}'
        )

        header = WebhookSigner(["whsec_exemple_0123456789abcdef01234567"]).header(
            1_790_000_000, body
        )

        assert header == (
            "t=1790000000,v1=21fa5b167eea0d087d55bd99aa776360368b23f1ff542077eaee49f7618acd9e"
        )

    def test_during_a_rotation_both_secrets_sign_the_same_message(self) -> None:
        header = WebhookSigner([SECRET, OLD_SECRET]).header(NOW, BODY)

        assert header == (
            f"t={NOW},v1={_expected(SECRET, NOW, BODY)},v1={_expected(OLD_SECRET, NOW, BODY)}"
        )

    def test_a_signer_needs_at_least_one_non_empty_secret(self) -> None:
        with pytest.raises(ValueError, match="secret"):
            WebhookSigner([])
        with pytest.raises(ValueError, match="secret"):
            WebhookSigner([""])

    def test_the_repr_never_shows_a_secret(self) -> None:
        assert SECRET not in repr(WebhookSigner([SECRET]))


class TestVerification:
    def test_a_fresh_untouched_message_is_accepted(self) -> None:
        signer = WebhookSigner([SECRET])

        assert signer.verify(signer.header(NOW, BODY), BODY, now=NOW + 10) is True

    def test_a_tampered_body_is_rejected(self) -> None:
        signer = WebhookSigner([SECRET])

        assert signer.verify(signer.header(NOW, BODY), BODY + " ", now=NOW) is False

    def test_another_secret_is_rejected(self) -> None:
        header = WebhookSigner([OLD_SECRET]).header(NOW, BODY)

        assert WebhookSigner([SECRET]).verify(header, BODY, now=NOW) is False

    def test_a_modified_timestamp_is_rejected_because_it_is_part_of_the_signature(self) -> None:
        signer = WebhookSigner([SECRET])
        signature = signer.header(NOW, BODY).split("v1=")[1]

        assert signer.verify(f"t={NOW + 1},v1={signature}", BODY, now=NOW) is False

    @pytest.mark.parametrize("offset", [-301, 301, -3600, 3600])
    def test_a_timestamp_more_than_five_minutes_away_is_rejected(self, offset: int) -> None:
        signer = WebhookSigner([SECRET])

        assert signer.verify(signer.header(NOW, BODY), BODY, now=NOW + offset) is False

    @pytest.mark.parametrize("offset", [-300, 0, 300])
    def test_the_tolerance_is_five_minutes_either_side(self, offset: int) -> None:
        signer = WebhookSigner([SECRET])

        assert signer.verify(signer.header(NOW, BODY), BODY, now=NOW + offset) is True

    def test_a_receiver_accepts_the_message_when_any_of_the_signatures_matches(self) -> None:
        rotating = WebhookSigner([SECRET, OLD_SECRET]).header(NOW, BODY)

        assert WebhookSigner([OLD_SECRET]).verify(rotating, BODY, now=NOW) is True
        assert WebhookSigner([SECRET]).verify(rotating, BODY, now=NOW) is True

    @pytest.mark.parametrize(
        "header",
        ["", "garbage", "t=abc,v1=00", f"t={NOW}", "v1=00", f"t={NOW},v1=", f"t=,v1={'0' * 64}"],
    )
    def test_a_malformed_header_is_rejected_without_raising(self, header: str) -> None:
        assert WebhookSigner([SECRET]).verify(header, BODY, now=NOW) is False

    def test_the_comparison_is_constant_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, str]] = []
        real = hmac.compare_digest

        def spy(first: str, second: str) -> bool:
            calls.append((first, second))
            return real(first, second)

        monkeypatch.setattr(hmac, "compare_digest", spy)
        signer = WebhookSigner([SECRET])

        signer.verify(signer.header(NOW, BODY), BODY, now=NOW)

        assert calls
