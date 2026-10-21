import hashlib
import re

from argon2 import PasswordHasher as Argon2

from app.registration.infrastructure.clients.argon2_password_hasher import Argon2PasswordHasher
from app.registration.infrastructure.clients.file_common_password_list import (
    FileCommonPasswordList,
)
from app.registration.infrastructure.clients.secure_token_generator import SecureTokenGenerator
from app.registration.infrastructure.clients.system_clock import SystemClock


class TestArgon2PasswordHasher:
    def test_produces_an_argon2id_hash_that_verifies(self) -> None:
        hashed = Argon2PasswordHasher().hash("sentier-du-mont-blanc")

        assert hashed.startswith("$argon2id$")
        assert Argon2().verify(hashed, "sentier-du-mont-blanc") is True

    def test_never_contains_the_password_and_is_salted(self) -> None:
        hasher = Argon2PasswordHasher()

        first, second = hasher.hash("sentier-du-mont-blanc"), hasher.hash("sentier-du-mont-blanc")

        assert "sentier" not in first
        assert first != second


class TestSecureTokenGenerator:
    def test_tokens_are_long_unique_and_url_safe(self) -> None:
        generator = SecureTokenGenerator()

        tokens = {generator.generate() for _ in range(50)}

        assert len(tokens) == 50
        assert all(len(token) >= 43 and re.fullmatch(r"[A-Za-z0-9_-]+", token) for token in tokens)

    def test_digest_is_the_sha256_hex_of_the_token(self) -> None:
        digest = SecureTokenGenerator().digest("abc")

        assert digest == hashlib.sha256(b"abc").hexdigest()
        assert len(digest) == 64


class TestFileCommonPasswordList:
    def test_knows_common_passwords_whatever_the_case(self) -> None:
        passwords = FileCommonPasswordList()

        assert passwords.contains("Password1234")
        assert passwords.contains("MOTDEPASSE123")

    def test_does_not_flag_an_uncommon_passphrase(self) -> None:
        assert not FileCommonPasswordList().contains("sentier-du-mont-blanc")

    def test_ignores_blank_lines(self) -> None:
        assert not FileCommonPasswordList().contains("")


class TestSystemClock:
    def test_returns_a_timezone_aware_utc_instant(self) -> None:
        offset = SystemClock().now().utcoffset()

        assert offset is not None
        assert offset.total_seconds() == 0
