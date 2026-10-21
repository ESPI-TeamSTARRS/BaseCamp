from datetime import timedelta

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.lockout.__tests__.fakes import (
    FIVE_IN_FIFTEEN,
    START,
    FakeLockoutUnitOfWork,
    LockoutStore,
)
from app.lockout.application.lockout_service import LockoutService

SUBJECT = "fp-camille"
STEP = timedelta(seconds=10)


class Setup:
    def __init__(self) -> None:
        self.store = LockoutStore()
        self.events = InMemoryBusinessEventLogger()
        self.service = LockoutService(
            lambda: FakeLockoutUnitOfWork(self.store), FIVE_IN_FIFTEEN, self.events
        )

    def fail(self, times: int, scope: str = "password", subject: str = SUBJECT, start=START):  # type: ignore[no-untyped-def]
        status = None
        for index in range(times):
            status = self.service.record_failure(scope, subject, start + index * STEP)
        return status


class TestCheck:
    def test_an_unknown_subject_is_free(self) -> None:
        assert not Setup().service.check("password", SUBJECT, START).locked

    def test_four_failures_leave_the_subject_free(self) -> None:
        setup = Setup()

        status = setup.fail(4)

        assert status is not None and not status.locked
        assert not setup.service.check("password", SUBJECT, START + 4 * STEP).locked

    def test_the_fifth_failure_locks_for_fifteen_minutes(self) -> None:
        setup = Setup()

        status = setup.fail(5)

        assert status is not None
        assert (status.locked, status.just_locked, status.retry_after_seconds) == (True, True, 900)
        check = setup.service.check("password", SUBJECT, START + 5 * STEP)
        assert (check.locked, check.just_locked) == (True, False)
        assert 0 < check.retry_after_seconds <= 900

    def test_the_lock_expires_by_itself(self) -> None:
        setup = Setup()
        setup.fail(5)

        assert not setup.service.check("password", SUBJECT, START + timedelta(minutes=16)).locked

    def test_a_failure_while_locked_reports_the_lock_without_a_new_event(self) -> None:
        setup = Setup()
        setup.fail(5)
        setup.events.events.clear()

        status = setup.service.record_failure("password", SUBJECT, START + timedelta(minutes=5))

        assert status.locked and not status.just_locked
        assert setup.events.events == []


class TestSuccess:
    def test_a_success_resets_the_counter(self) -> None:
        setup = Setup()
        setup.fail(4)

        setup.service.record_success("password", SUBJECT)
        status = setup.fail(4, start=START + timedelta(minutes=1))

        assert status is not None and not status.locked

    def test_a_success_forgets_the_ladder(self) -> None:
        setup = Setup()
        setup.fail(5)
        later = START + timedelta(minutes=20)
        setup.service.record_success("password", SUBJECT)

        status = setup.fail(5, start=later)

        assert status is not None and status.retry_after_seconds == 900

    def test_a_success_without_history_is_harmless(self) -> None:
        setup = Setup()

        setup.service.record_success("password", SUBJECT)

        assert setup.store.rows == {}


class TestIndependence:
    def test_each_step_and_each_subject_counts_on_its_own(self) -> None:
        setup = Setup()

        setup.fail(5, scope="password")

        assert setup.service.check("password", SUBJECT, START + 6 * STEP).locked
        assert not setup.service.check("face", SUBJECT, START + 6 * STEP).locked
        assert not setup.service.check("password", "other", START + 6 * STEP).locked

    def test_the_step_is_a_free_label_for_future_stages(self) -> None:
        setup = Setup()

        status = setup.fail(5, scope="face")

        assert status is not None and status.locked


class TestAttackerCap:
    def test_repeated_lockouts_never_exceed_the_last_step(self) -> None:
        setup = Setup()
        now = START
        longest = 0
        for _ in range(8):
            status = setup.fail(5, start=now)
            assert status is not None
            longest = max(longest, status.retry_after_seconds)
            now += timedelta(seconds=40 + status.retry_after_seconds + 60)

        assert longest == 3600


class TestEvents:
    def test_locking_emits_one_event_with_the_step_and_no_account_data(self) -> None:
        setup = Setup()

        setup.fail(5, scope="face")

        [event] = setup.events.events
        assert (event.event, event.outcome, event.reason) == (
            "auth.lockout_triggered",
            Outcome.DENIED,
            "too_many_failures",
        )
        assert dict(event.attributes) == {
            "step": "face",
            "subject_hash": SUBJECT,
            "level": 1,
            "locked_seconds": 900,
        }

    def test_no_event_before_the_threshold(self) -> None:
        setup = Setup()

        setup.fail(4)

        assert setup.events.events == []


class TestHousekeeping:
    def test_idle_subjects_are_purged_after_the_memory_period(self) -> None:
        setup = Setup()
        setup.service.record_failure("password", "old", START)

        setup.service.record_failure("password", "new", START + timedelta(hours=25))

        assert {key[1] for key in setup.store.rows} == {"new"}

    def test_a_subject_still_locked_is_never_purged(self) -> None:
        setup = Setup()
        setup.fail(5, subject="locked")

        setup.service.record_failure("password", "new", START + timedelta(minutes=10))

        assert ("password", "locked") in setup.store.rows
