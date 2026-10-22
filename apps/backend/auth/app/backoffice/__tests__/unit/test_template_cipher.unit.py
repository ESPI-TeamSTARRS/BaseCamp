import base64
from pathlib import Path
from uuid import uuid4

import pytest

from app.backoffice.__tests__.cipher import TEST_KEY
from app.backoffice.domain.exceptions.gabarit_invalide import GabaritInvalide
from app.backoffice.infrastructure.clients.aes_gcm_template_cipher import (
    NONCE_BYTES,
    AesGcmTemplateCipher,
)
from app.backoffice.infrastructure.clients.face_template_key_file import load_template_cipher

TEMPLATE = bytes(range(256)) * 8 + b"x" * 21  # 2 069 octets


class TestAesGcmTemplateCipher:
    def test_a_template_round_trips_for_its_account(self) -> None:
        cipher, account = AesGcmTemplateCipher(TEST_KEY), uuid4()

        stored = cipher.encrypt(account, TEMPLATE)

        assert cipher.decrypt(account, stored) == TEMPLATE

    def test_the_stored_bytes_never_contain_the_template(self) -> None:
        cipher, account = AesGcmTemplateCipher(TEST_KEY), uuid4()

        stored = cipher.encrypt(account, TEMPLATE)

        assert TEMPLATE not in stored and TEMPLATE[:32] not in stored
        assert len(stored) == 1 + NONCE_BYTES + len(TEMPLATE) + 16

    def test_each_encryption_uses_a_fresh_nonce(self) -> None:
        cipher, account = AesGcmTemplateCipher(TEST_KEY), uuid4()

        first = cipher.encrypt(account, TEMPLATE)
        second = cipher.encrypt(account, TEMPLATE)

        assert first != second

    def test_a_template_copied_to_another_account_does_not_decrypt(self) -> None:
        cipher = AesGcmTemplateCipher(TEST_KEY)
        stored = cipher.encrypt(uuid4(), TEMPLATE)

        with pytest.raises(GabaritInvalide):
            cipher.decrypt(uuid4(), stored)

    def test_another_key_does_not_decrypt(self) -> None:
        account = uuid4()
        stored = AesGcmTemplateCipher(TEST_KEY).encrypt(account, TEMPLATE)

        with pytest.raises(GabaritInvalide):
            AesGcmTemplateCipher(bytes(reversed(TEST_KEY))).decrypt(account, stored)

    @pytest.mark.parametrize("position", [0, 1, 13, -1])
    def test_a_tampered_byte_is_refused(self, position: int) -> None:
        cipher, account = AesGcmTemplateCipher(TEST_KEY), uuid4()
        stored = bytearray(cipher.encrypt(account, TEMPLATE))
        stored[position] ^= 0x01

        with pytest.raises(GabaritInvalide):
            cipher.decrypt(account, bytes(stored))

    @pytest.mark.parametrize("stored", [b"", b"\x01", b"\x01" + b"\x00" * NONCE_BYTES])
    def test_a_truncated_content_is_refused(self, stored: bytes) -> None:
        with pytest.raises(GabaritInvalide):
            AesGcmTemplateCipher(TEST_KEY).decrypt(uuid4(), stored)

    @pytest.mark.parametrize("size", [0, 16, 31, 33, 64])
    def test_the_key_must_be_32_bytes(self, size: int) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            AesGcmTemplateCipher(b"k" * size)


class TestKeyFile:
    def _write(self, tmp_path: Path, text: str) -> str:
        path = tmp_path / "face.key"
        path.write_text(text, encoding="ascii")
        return str(path)

    def test_a_base64_key_is_loaded_with_its_trailing_newline(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, base64.b64encode(TEST_KEY).decode() + "\n")
        account = uuid4()

        cipher = load_template_cipher(path)

        assert cipher.decrypt(account, AesGcmTemplateCipher(TEST_KEY).encrypt(account, b"x" * 40))

    def test_a_missing_file_stops_the_start_without_naming_a_secret(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="missing or unreadable"):
            load_template_cipher(str(tmp_path / "absent.key"))

    @pytest.mark.parametrize("text", ["pas du base64 !!", "", base64.b64encode(b"court").decode()])
    def test_a_bad_key_is_refused_and_never_echoed(self, tmp_path: Path, text: str) -> None:
        with pytest.raises(ValueError) as raised:
            load_template_cipher(self._write(tmp_path, text))

        assert text.strip() == "" or text not in str(raised.value)
