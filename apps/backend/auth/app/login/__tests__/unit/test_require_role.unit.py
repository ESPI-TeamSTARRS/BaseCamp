from uuid import uuid4

import pytest

from app.login.application.principal import Principal
from app.login.presentation.require_role import require_role


class TestRequireRole:
    def test_at_least_one_role_is_needed(self) -> None:
        with pytest.raises(ValueError, match="at least one role"):
            require_role()

    def test_a_principal_matches_any_of_the_accepted_roles(self) -> None:
        principal = Principal(uuid4(), ("customer",))

        assert principal.has_any(frozenset({"operator", "customer"}))
        assert not principal.has_any(frozenset({"operator"}))
