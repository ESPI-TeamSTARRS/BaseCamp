from app.lockout.domain.entities.lockout_state import LockoutState
from app.lockout.infrastructure.models.login_lockout_model import LoginLockoutModel


class LockoutMapper:
    @staticmethod
    def to_entity(model: LoginLockoutModel) -> LockoutState:
        return LockoutState(
            scope=model.scope,
            subject=model.subject,
            failures=model.failures,
            window_started_at=model.window_started_at,
            level=model.level,
            locked_until=model.locked_until,
            updated_at=model.updated_at,
        )

    @staticmethod
    def apply(model: LoginLockoutModel, state: LockoutState) -> None:
        model.failures = state.failures
        model.window_started_at = state.window_started_at
        model.level = state.level
        model.locked_until = state.locked_until
        if state.updated_at is not None:
            model.updated_at = state.updated_at
