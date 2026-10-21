import hashlib
import re
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher as Argon2

from app.core.logging.email_pseudonymizer import EmailPseudonymizer
from app.login.infrastructure.clients.argon2_password_verifier import Argon2PasswordVerifier
from app.login.infrastructure.clients.hmac_email_fingerprinter import HmacEmailFingerprinter
from app.login.infrastructure.clients.secure_refresh_token_generator import (
    SecureRefreshTokenGenerator,
)
from app.login.infrastructure.clients.system_clock import SystemClock

PASSWORD = "sentier-du-mont-blanc"
CHEAP = Argon2(time_cost=1, memory_cost=8, parallelism=1)


class TestArgon2PasswordVerifier:
    def test_verifies_a_hash_made_by_the_registration_parameters(self) -> None:
        verifier = Argon2PasswordVerifier()
        stored = Argon2().hash(PASSWORD)

        assert verifier.verify(stored, PASSWORD) is True
        assert verifier.verify(stored, "autre-phrase-de-passe") is False

    def test_a_malformed_hash_never_verifies(self) -> None:
        assert Argon2PasswordVerifier().verify("pas-un-hachage", PASSWORD) is False

    def test_the_decoy_runs_a_real_argon2id_verification_and_never_raises(self) -> None:
        Argon2PasswordVerifier().verify_decoy(PASSWORD)

    def test_the_decoy_hash_is_unrelated_to_any_password(self) -> None:
        verifier = Argon2PasswordVerifier()

        assert Argon2PasswordVerifier().verify(verifier.decoy_hash, PASSWORD) is False

    def test_hashing_produces_a_salted_argon2id_hash(self) -> None:
        verifier = Argon2PasswordVerifier()

        first, second = verifier.hash(PASSWORD), verifier.hash(PASSWORD)

        assert first.startswith("$argon2id$")
        assert first != second
        assert verifier.verify(first, PASSWORD)

    def test_a_hash_with_the_current_parameters_does_not_need_a_rehash(self) -> None:
        verifier = Argon2PasswordVerifier()

        assert verifier.needs_rehash(verifier.hash(PASSWORD)) is False

    def test_a_hash_made_with_weaker_parameters_needs_a_rehash(self) -> None:
        weaker = CHEAP.hash(PASSWORD)

        assert Argon2PasswordVerifier().needs_rehash(weaker) is True

    def test_a_hash_made_with_other_parameters_is_still_accepted(self) -> None:
        assert Argon2PasswordVerifier().verify(CHEAP.hash(PASSWORD), PASSWORD) is True

    def test_a_malformed_hash_does_not_ask_for_a_rehash(self) -> None:
        assert Argon2PasswordVerifier().needs_rehash("pas-un-hachage") is False


class TestSecureRefreshTokenGenerator:
    def test_tokens_are_long_unique_and_url_safe(self) -> None:
        generator = SecureRefreshTokenGenerator()

        tokens = {generator.generate() for _ in range(50)}

        assert len(tokens) == 50
        assert all(len(token) >= 43 and re.fullmatch(r"[A-Za-z0-9_-]+", token) for token in tokens)

    def test_digest_is_the_sha256_hex_of_the_token(self) -> None:
        assert SecureRefreshTokenGenerator().digest("abc") == hashlib.sha256(b"abc").hexdigest()


class TestHmacEmailFingerprinter:
    def test_is_stable_and_never_the_address(self) -> None:
        fingerprinter = HmacEmailFingerprinter(EmailPseudonymizer("une-cle-de-test"))

        first = fingerprinter.fingerprint("camille@example.com")

        assert first == fingerprinter.fingerprint("camille@example.com")
        assert len(first) == 16
        assert "camille" not in first


class TestSystemClock:
    def test_now_is_utc_and_current(self) -> None:
        now = SystemClock().now()

        assert now.tzinfo is UTC
        assert abs(datetime.now(UTC) - now) < timedelta(seconds=5)
