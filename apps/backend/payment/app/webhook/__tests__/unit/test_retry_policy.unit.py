from datetime import timedelta

import pytest

from app.webhook.domain.value_objects.retry_policy import RetryPolicy


class TestRetryPolicy:
    def test_the_wait_doubles_after_each_failed_attempt(self) -> None:
        policy = RetryPolicy(max_attempts=6, base_seconds=5, max_delay_seconds=300)

        waits = [policy.delay_after(attempt) for attempt in range(1, 6)]

        assert waits == [timedelta(seconds=s) for s in (5, 10, 20, 40, 80)]

    def test_the_wait_is_capped(self) -> None:
        policy = RetryPolicy(max_attempts=10, base_seconds=5, max_delay_seconds=60)

        assert policy.delay_after(9) == timedelta(seconds=60)

    def test_the_defaults_give_six_attempts(self) -> None:
        assert RetryPolicy().max_attempts == 6

    def test_the_budget_is_exhausted_at_the_last_attempt(self) -> None:
        policy = RetryPolicy(max_attempts=3, base_seconds=1, max_delay_seconds=10)

        assert [policy.is_exhausted(n) for n in (1, 2, 3, 4)] == [False, False, True, True]

    @pytest.mark.parametrize(
        ("attempts", "base", "cap"), [(0, 1, 10), (3, 0, 10), (3, 1, 0), (3, 20, 10)]
    )
    def test_invalid_values_are_refused(self, attempts: int, base: float, cap: float) -> None:
        with pytest.raises(ValueError, match="retry"):
            RetryPolicy(max_attempts=attempts, base_seconds=base, max_delay_seconds=cap)
