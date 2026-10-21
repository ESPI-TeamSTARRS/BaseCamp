from datetime import datetime, timedelta
from typing import Any

import pytest

from app.lockout.__tests__.fakes import FIVE_IN_FIFTEEN, START
from app.lockout.domain.entities.lockout_policy import LockoutPolicy
from app.lockout.domain.entities.lockout_state import LockoutState

MINUTE = timedelta(minutes=1)


def until(state: LockoutState) -> datetime:
    assert state.locked_until is not None
    return state.locked_until


def fail(
    state: LockoutState,
    times: int,
    start: datetime = START,
    every: timedelta = timedelta(seconds=10),
) -> LockoutState:
    for index in range(times):
        state = state.after_failure(start + index * every, FIVE_IN_FIFTEEN)
    return state


class TestPolicy:
    def test_the_ladder_is_capped_by_its_last_step(self) -> None:
        assert [FIVE_IN_FIFTEEN.duration_for(level) for level in (1, 2, 3, 4, 9)] == [
            15 * MINUTE,
            30 * MINUTE,
            60 * MINUTE,
            60 * MINUTE,
            60 * MINUTE,
        ]

    def test_a_single_retry_then_five_minutes_is_a_matter_of_settings(self) -> None:
        policy = LockoutPolicy(2, 5 * MINUTE, (5 * MINUTE,), timedelta(hours=1))
        state = LockoutState("face", "s")

        state = state.after_failure(START, policy)
        assert not state.locked(START)
        state = state.after_failure(START + MINUTE, policy)

        assert state.locked(START + MINUTE)
        assert state.retry_after_seconds(START + MINUTE) == 300

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"max_failures": 0}, "max_failures"),
            ({"window": timedelta(0)}, "window"),
            ({"memory": timedelta(0)}, "window"),
            ({"durations": ()}, "durations"),
            ({"durations": (timedelta(0),)}, "durations"),
        ],
    )
    def test_an_invalid_policy_is_refused(self, kwargs: dict[str, Any], message: str) -> None:
        base: dict[str, Any] = {
            "max_failures": 5,
            "window": 15 * MINUTE,
            "durations": (15 * MINUTE,),
            "memory": timedelta(hours=1),
        }

        with pytest.raises(ValueError, match=message):
            LockoutPolicy(**{**base, **kwargs})


class TestFailures:
    def test_four_failures_do_not_lock(self) -> None:
        state = fail(LockoutState("password", "s"), 4)

        assert not state.locked(START + 40 * timedelta(seconds=1))
        assert state.failures == 4

    def test_the_fifth_failure_in_the_window_locks_for_fifteen_minutes(self) -> None:
        state = fail(LockoutState("password", "s"), 5)
        now = START + timedelta(seconds=40)

        assert state.locked(now)
        assert state.level == 1
        assert state.retry_after_seconds(now) == 15 * 60 - 0
        assert state.failures == 0

    def test_failures_outside_the_window_start_a_new_count(self) -> None:
        state = fail(LockoutState("password", "s"), 4)

        state = state.after_failure(START + 16 * MINUTE, FIVE_IN_FIFTEEN)

        assert state.failures == 1
        assert not state.locked(START + 16 * MINUTE)

    def test_a_failure_during_the_lock_neither_counts_nor_extends_it(self) -> None:
        locked = fail(LockoutState("password", "s"), 5)
        during = START + 5 * MINUTE

        assert locked.after_failure(during, FIVE_IN_FIFTEEN) == locked

    def test_a_relapse_climbs_the_ladder_up_to_the_cap(self) -> None:
        state = LockoutState("password", "s")
        now = START
        durations = []
        for _ in range(5):
            state = fail(state, 5, start=now)
            durations.append(state.retry_after_seconds(now + timedelta(seconds=40)) // 60)
            now = until(state) + MINUTE

        assert durations == [15, 30, 60, 60, 60]

    def test_the_ladder_is_forgotten_after_the_memory_period(self) -> None:
        state = fail(LockoutState("password", "s"), 5)
        later = until(state) + timedelta(hours=25)

        state = fail(state, 5, start=later)

        assert state.level == 1
        assert state.retry_after_seconds(later + timedelta(seconds=40)) == 15 * 60 - 0

    def test_expiry_of_the_lock_frees_the_subject(self) -> None:
        state = fail(LockoutState("password", "s"), 5)

        assert not state.locked(until(state))
        assert state.retry_after_seconds(until(state)) == 0
