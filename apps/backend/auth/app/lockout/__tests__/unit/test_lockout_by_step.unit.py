from datetime import timedelta

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.lockout.__tests__.fakes import (
    FIVE_IN_FIFTEEN,
    START,
    FakeLockoutUnitOfWork,
    LockoutStore,
)
from app.lockout.application.lockout_service import LockoutService
from app.lockout.domain.entities.lockout_policies import LockoutPolicies
from app.lockout.domain.entities.lockout_policy import LockoutPolicy
from app.lockout.domain.entities.lockout_subject import LockoutSubject
from app.lockout.domain.enums.subject_type import SubjectType

MINUTE = timedelta(minutes=1)
STEP = timedelta(seconds=10)
FIXED_5_MIN = timedelta(minutes=5)
SUBJECT = "fp-operator"
ADDRESS = "fp-address"


def _fixed(max_failures: int) -> LockoutPolicy:
    """N echecs puis 5 minutes fixes, sans escalade."""
    return LockoutPolicy(max_failures, 10 * MINUTE, (FIXED_5_MIN,), FIXED_5_MIN)


POLICIES = LockoutPolicies(
    default=FIVE_IN_FIFTEEN,
    address=_fixed(20),
    steps={
        ("operator_password", SubjectType.ACCOUNT): _fixed(3),
        ("face", SubjectType.ACCOUNT): _fixed(5),
    },
)


class Setup:
    def __init__(self, policies: LockoutPolicies = POLICIES) -> None:
        self.store = LockoutStore()
        self.events = InMemoryBusinessEventLogger()
        self.service = LockoutService(
            lambda: FakeLockoutUnitOfWork(self.store), policies, self.events
        )

    def fail(self, step: str, times: int, subject: str = SUBJECT, **kwargs):  # type: ignore[no-untyped-def]
        status = None
        for index in range(times):
            status = self.service.record_failure(step, subject, START + index * STEP, **kwargs)
        return status


class TestPolicyPerStep:
    def test_the_password_step_locks_after_three_failures_for_five_fixed_minutes(self) -> None:
        setup = Setup()

        two = setup.fail("operator_password", 2)
        three = Setup().fail("operator_password", 3)

        assert two is not None and not two.locked
        assert three is not None
        assert (three.locked, three.retry_after_seconds) == (True, 300)

    def test_the_face_step_tolerates_four_failures_and_locks_on_the_fifth(self) -> None:
        setup = Setup()

        four = setup.fail("face", 4)
        five = Setup().fail("face", 5)

        assert four is not None and not four.locked
        assert five is not None
        assert (five.locked, five.retry_after_seconds) == (True, 300)

    def test_a_relock_stays_five_minutes_without_escalation(self) -> None:
        setup = Setup()
        setup.fail("operator_password", 3)
        later = START + 10 * MINUTE

        status = None
        for index in range(3):
            status = setup.service.record_failure(
                "operator_password", SUBJECT, later + index * STEP
            )

        assert status is not None
        assert status.retry_after_seconds == 300

    def test_an_unconfigured_step_keeps_the_default_policy(self) -> None:
        setup = Setup()

        four = setup.fail("password", 4)
        five = Setup().fail("password", 5)

        assert four is not None and not four.locked
        assert five is not None
        assert (five.locked, five.retry_after_seconds) == (True, 900)

    def test_a_single_policy_still_applies_to_every_step(self) -> None:
        setup = Setup(LockoutPolicies(default=FIVE_IN_FIFTEEN))

        status = setup.fail("anything", 5)

        assert status is not None and status.locked


class TestSeparateCounters:
    def test_refused_faces_never_count_as_wrong_passwords(self) -> None:
        setup = Setup()
        setup.fail("face", 4)

        status = setup.fail("operator_password", 2)

        assert status is not None and not status.locked
        assert not setup.service.check("face", SUBJECT, START + 5 * STEP).locked

    def test_wrong_passwords_never_count_as_refused_faces(self) -> None:
        setup = Setup()
        setup.fail("operator_password", 3)

        assert setup.service.check("operator_password", SUBJECT, START + 4 * STEP).locked
        assert not setup.service.check("face", SUBJECT, START + 4 * STEP).locked

    def test_two_accounts_have_their_own_counters(self) -> None:
        setup = Setup()
        setup.fail("operator_password", 3, subject="fp-other")

        assert not setup.service.check("operator_password", SUBJECT, START + 4 * STEP).locked


class TestSourceAddress:
    def test_an_address_has_its_own_thresholds(self) -> None:
        setup = Setup()

        nineteen = setup.fail(
            "operator_password", 19, subject=ADDRESS, subject_type=SubjectType.SOURCE_ADDRESS
        )
        twenty = Setup().fail(
            "operator_password", 20, subject=ADDRESS, subject_type=SubjectType.SOURCE_ADDRESS
        )

        assert nineteen is not None and not nineteen.locked
        assert twenty is not None
        assert (twenty.locked, twenty.retry_after_seconds) == (True, 300)

    def test_the_address_counter_is_not_the_account_counter(self) -> None:
        setup = Setup()
        setup.fail("operator_password", 3, subject=ADDRESS, subject_type=SubjectType.SOURCE_ADDRESS)

        assert not setup.service.check("operator_password", ADDRESS, START + 4 * STEP).locked

    def test_a_blocked_address_is_reported_whatever_the_account(self) -> None:
        setup = Setup()
        setup.fail("face", 20, subject=ADDRESS, subject_type=SubjectType.SOURCE_ADDRESS)
        now = START + 21 * STEP

        blocked = setup.service.check("face", ADDRESS, now, subject_type=SubjectType.SOURCE_ADDRESS)

        assert blocked.locked
        # rien de l'etat du compte n'entre dans la reponse d'une adresse bloquee
        assert set(vars(blocked)) == {"locked", "retry_after_seconds", "just_locked"}

    def test_the_address_policy_falls_back_to_the_default_when_not_given(self) -> None:
        setup = Setup(LockoutPolicies(default=FIVE_IN_FIFTEEN))

        status = setup.fail("face", 5, subject=ADDRESS, subject_type=SubjectType.SOURCE_ADDRESS)

        assert status is not None and status.locked


class TestReset:
    def test_a_complete_login_clears_every_counter_of_the_person(self) -> None:
        setup = Setup()
        setup.fail("operator_password", 2)
        setup.fail("face", 4)
        setup.fail("face", 4, subject=ADDRESS, subject_type=SubjectType.SOURCE_ADDRESS)

        setup.service.clear(
            [
                LockoutSubject("operator_password", SUBJECT),
                LockoutSubject("face", SUBJECT),
                LockoutSubject("face", ADDRESS, SubjectType.SOURCE_ADDRESS),
            ]
        )

        assert setup.store.rows == {}

    def test_clearing_is_one_transaction(self) -> None:
        setup = Setup()
        setup.fail("operator_password", 1)
        commits = setup.store.commits

        setup.service.clear(
            [LockoutSubject("operator_password", SUBJECT), LockoutSubject("face", SUBJECT)]
        )

        assert setup.store.commits == commits + 1


class TestBlockEvent:
    def test_the_event_carries_step_subject_type_and_a_truncated_address(self) -> None:
        setup = Setup()

        setup.fail("operator_password", 3, client_ip="203.0.113.77")

        (event,) = setup.events.events
        assert event.event == "auth.lockout_triggered"
        assert event.attributes["step"] == "operator_password"
        assert event.attributes["subject_type"] == "account"
        assert event.attributes["subject_hash"] == SUBJECT
        assert event.client_ip == "203.0.113.0/24"
        assert "203.0.113.77" not in repr(event)

    def test_an_address_block_event_names_its_subject_type(self) -> None:
        setup = Setup()

        setup.fail(
            "face",
            20,
            subject=ADDRESS,
            subject_type=SubjectType.SOURCE_ADDRESS,
            client_ip="2001:db8:1234:5678::1",
        )

        (event,) = setup.events.events
        assert event.attributes["subject_type"] == "address"
        assert event.client_ip == "2001:db8:1234::/48"

    @pytest.mark.parametrize("bad", [None, "", "not-an-ip", "999.1.1.1"])
    def test_no_usable_address_means_no_address_in_the_event(self, bad: str | None) -> None:
        setup = Setup()

        setup.fail("operator_password", 3, client_ip=bad)

        (event,) = setup.events.events
        assert event.client_ip is None

    def test_failures_below_the_threshold_log_nothing(self) -> None:
        setup = Setup()

        setup.fail("operator_password", 2)

        assert setup.events.events == []


class TestPolicies:
    def test_the_longest_memory_bounds_the_purge(self) -> None:
        assert POLICIES.max_memory == FIVE_IN_FIFTEEN.memory

    def test_scopes_of_different_subject_types_never_collide(self) -> None:
        from app.lockout.domain.entities.lockout_scope import lockout_scope

        assert lockout_scope("face", SubjectType.ACCOUNT) == "face"
        assert lockout_scope("face", SubjectType.SOURCE_ADDRESS) == "face@address"
        assert len(lockout_scope("operator_password", SubjectType.SOURCE_ADDRESS)) <= 32
