"""Chiffreur de gabarits des tests (cle jetable, jamais une vraie cle)."""

from app.backoffice.infrastructure.clients.aes_gcm_template_cipher import AesGcmTemplateCipher

TEST_KEY = bytes(range(32))
TEST_CIPHER = AesGcmTemplateCipher(TEST_KEY)
