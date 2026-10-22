from datetime import timedelta

from app.core.config import Settings
from app.lockout.composition import build_lockout_policies
from app.lockout.domain.enums.subject_type import SubjectType

MINUTE = timedelta(minutes=1)


class TestBuildLockoutPolicies:
    def test_the_existing_steps_keep_the_client_login_defaults(self) -> None:
        policies = build_lockout_policies(Settings())

        password = policies.for_step("password")

        assert password.max_failures == 5
        assert password.window == 15 * MINUTE
        assert password.durations == (15 * MINUTE, 30 * MINUTE, 60 * MINUTE)

    def test_the_operator_password_step_is_three_failures_then_five_fixed_minutes(self) -> None:
        policy = build_lockout_policies(Settings()).for_step("operator_password")

        assert policy.max_failures == 3
        assert policy.durations == (5 * MINUTE,)

    def test_the_face_step_is_five_failures_then_five_fixed_minutes(self) -> None:
        policy = build_lockout_policies(Settings()).for_step("face")

        assert policy.max_failures == 5
        assert policy.durations == (5 * MINUTE,)

    def test_the_source_address_has_its_own_policy_for_every_step(self) -> None:
        policies = build_lockout_policies(Settings())

        for step in ("password", "operator_password", "face"):
            assert policies.for_step(step, SubjectType.SOURCE_ADDRESS).max_failures == 20

    def test_the_policy_follows_the_settings(self) -> None:
        settings = Settings(lockout_face_max_failures=9, lockout_address_duration_seconds=60)

        policies = build_lockout_policies(settings)

        assert policies.for_step("face").max_failures == 9
        assert policies.for_step("face", SubjectType.SOURCE_ADDRESS).durations == (MINUTE,)

    def test_the_invitation_step_is_bound_to_the_address_five_failures_then_five_minutes(
        self,
    ) -> None:
        policy = build_lockout_policies(Settings()).for_step(
            "invitation", SubjectType.SOURCE_ADDRESS
        )

        assert policy.max_failures == 5
        assert policy.window == 10 * MINUTE
        assert policy.durations == (5 * MINUTE,)
