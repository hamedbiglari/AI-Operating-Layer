"""Encryption at rest for AI provider credentials (REQ-AIC-008, ADR-088).
Fernet (AES-128-CBC + HMAC-SHA256) keyed by AI_CREDENTIAL_KEY from the
environment. No key configured = credentials cannot be stored (refused
honestly), never stored in clear."""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class CredentialKeyMissing(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = settings.AI_CREDENTIAL_KEY
    if key is None or not key.get_secret_value():
        raise CredentialKeyMissing("AI_CREDENTIAL_KEY is not configured")
    return Fernet(key.get_secret_value().encode())


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise CredentialKeyMissing("credential cannot be decrypted with the configured key") from None
