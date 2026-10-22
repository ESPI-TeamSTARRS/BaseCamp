import importlib.util
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from types import ModuleType

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.lockout.__tests__.fakes import FIVE_IN_FIFTEEN, START
from app.lockout.application.lockout_service import LockoutService
from app.lockout.infrastructure.models.lockout_base import LockoutBase
from app.lockout.infrastructure.repositories.sqlalchemy_lockout_unit_of_work import (
    SqlAlchemyLockoutUnitOfWork,
)

MIGRATION = Path(__file__).resolve().parents[4] / "alembic" / "versions" / "0009_login_lockouts.py"
SUBJECT = "fp-camille"


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("0009_login_lockouts", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migrated(engine: Engine) -> Engine:
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        load_migration().upgrade()
    return engine


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = migrated(
        create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
    )
    yield engine
    engine.dispose()


def service(engine: Engine) -> LockoutService:
    return LockoutService(
        lambda: SqlAlchemyLockoutUnitOfWork(engine),
        FIVE_IN_FIFTEEN,
        InMemoryBusinessEventLogger(),
    )


def rows(engine: Engine) -> list[tuple[str, str, int, int]]:
    with engine.connect() as connection:
        return [
            tuple(row)
            for row in connection.execute(
                text(
                    "SELECT scope, subject, failures, level FROM login_lockouts ORDER BY subject, scope"
                )
            )
        ]


class TestRepository:
    def test_failures_are_counted_and_the_lock_is_stored(self, engine: Engine) -> None:
        lockouts = service(engine)

        for index in range(5):
            status = lockouts.record_failure("password", SUBJECT, START + timedelta(seconds=index))

        assert status.locked and status.retry_after_seconds == 900
        with engine.connect() as connection:
            stored = connection.execute(
                text("SELECT failures, level, locked_until FROM login_lockouts")
            ).one()
        assert (stored.failures, stored.level) == (0, 1)
        assert str(stored.locked_until).startswith("2026-01-01 12:15:04")

    def test_the_lock_survives_a_restart_and_is_seen_by_another_instance(
        self, tmp_path: Path
    ) -> None:
        url = f"sqlite+pysqlite:///{tmp_path / 'auth.db'}"
        first = migrated(create_engine(url))
        for index in range(5):
            service(first).record_failure("password", SUBJECT, START + timedelta(seconds=index))
        first.dispose()

        second = create_engine(url)
        status = service(second).check("password", SUBJECT, START + timedelta(minutes=1))
        second.dispose()

        assert status.locked

    def test_a_success_deletes_the_row(self, engine: Engine) -> None:
        lockouts = service(engine)
        lockouts.record_failure("password", SUBJECT, START)

        lockouts.record_success("password", SUBJECT)

        assert rows(engine) == []

    def test_steps_and_subjects_have_their_own_rows(self, engine: Engine) -> None:
        lockouts = service(engine)

        lockouts.record_failure("password", "a", START)
        lockouts.record_failure("face", "a", START)
        lockouts.record_failure("password", "b", START)

        assert rows(engine) == [
            ("face", "a", 1, 0),
            ("password", "a", 1, 0),
            ("password", "b", 1, 0),
        ]

    def test_a_transaction_without_commit_changes_nothing(self, engine: Engine) -> None:
        with SqlAlchemyLockoutUnitOfWork(engine) as work:
            state = work.lockouts.lock_for_update("password", SUBJECT, START)
            work.lockouts.save(state.after_failure(START, FIVE_IN_FIFTEEN))

        assert rows(engine) == []

    def test_saving_before_locking_the_row_is_a_programming_error(self, engine: Engine) -> None:
        from app.lockout.domain.entities.lockout_state import LockoutState

        with SqlAlchemyLockoutUnitOfWork(engine) as work, pytest.raises(LookupError):
            work.lockouts.save(LockoutState("password", SUBJECT))

    def test_the_idle_rows_are_purged(self, engine: Engine) -> None:
        lockouts = service(engine)
        lockouts.record_failure("password", "old", START)

        lockouts.record_failure("password", "new", START + timedelta(hours=25))

        assert [row[1] for row in rows(engine)] == ["new"]


class TestConcurrency:
    def test_simultaneous_failures_of_the_same_subject_are_all_counted(
        self, tmp_path: Path
    ) -> None:
        engine = migrated(create_engine(f"sqlite+pysqlite:///{tmp_path / 'auth.db'}"))
        contenders = 8
        start = Barrier(contenders)

        def attempt(_: int) -> None:
            start.wait()
            service(engine).record_failure("password", SUBJECT, START)

        with ThreadPoolExecutor(contenders) as pool:
            list(pool.map(attempt, range(contenders)))

        [(scope, subject, failures, level)] = rows(engine)
        engine.dispose()
        assert (scope, subject) == ("password", SUBJECT)
        # 5 echecs verrouillent; les suivants arrivent pendant le verrou et ne comptent pas.
        assert level == 1
        assert failures == 0


class TestMigration:
    def test_it_follows_revision_0008(self) -> None:
        migration = load_migration()

        assert (migration.revision, migration.down_revision) == ("0009", "0008")

    def test_upgrade_matches_the_model(self, engine: Engine) -> None:
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            differences = compare_metadata(context, LockoutBase.metadata)

        assert differences == []

    def test_upgrade_only_adds_a_table_and_downgrade_removes_it(self) -> None:
        engine = create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                load_migration().upgrade()
                assert "login_lockouts" in inspect(connection).get_table_names()
                load_migration().downgrade()
            assert "login_lockouts" not in inspect(connection).get_table_names()
        engine.dispose()


class TestByStepAndAddress:
    def test_an_address_lock_has_its_own_row_and_survives_a_restart(self, tmp_path: Path) -> None:
        from app.lockout.domain.enums.subject_type import SubjectType

        url = f"sqlite+pysqlite:///{tmp_path / 'auth.db'}"
        first = migrated(create_engine(url))
        for index in range(5):
            service(first).record_failure(
                "face",
                "fp-address",
                START + timedelta(seconds=index),
                subject_type=SubjectType.SOURCE_ADDRESS,
            )
        service(first).record_failure("face", "fp-address", START)
        first.dispose()

        second = create_engine(url)
        address = service(second).check(
            "face", "fp-address", START + timedelta(minutes=1), SubjectType.SOURCE_ADDRESS
        )
        account = service(second).check("face", "fp-address", START + timedelta(minutes=1))
        stored = rows(second)
        second.dispose()

        assert address.locked
        assert not account.locked
        assert [row[0] for row in stored] == ["face", "face@address"]

    def test_clearing_several_counters_removes_only_those(self, engine: Engine) -> None:
        from app.lockout.domain.entities.lockout_subject import LockoutSubject
        from app.lockout.domain.enums.subject_type import SubjectType

        lockouts = service(engine)
        lockouts.record_failure("operator_password", "a", START)
        lockouts.record_failure("face", "a", START)
        lockouts.record_failure("face", "ip", START, SubjectType.SOURCE_ADDRESS)
        lockouts.record_failure("face", "b", START)

        lockouts.clear(
            [
                LockoutSubject("operator_password", "a"),
                LockoutSubject("face", "a"),
                LockoutSubject("face", "ip", SubjectType.SOURCE_ADDRESS),
            ]
        )

        assert rows(engine) == [("face", "b", 1, 0)]
