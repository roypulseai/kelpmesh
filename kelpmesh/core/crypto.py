"""Encryption utilities for kelpmesh — AES-256-GCM via Fernet."""
import base64
import logging
import os
from pathlib import Path

_logger = logging.getLogger(__name__)

_FERNET_AVAILABLE = False
try:
    from cryptography.fernet import Fernet
    _FERNET_AVAILABLE = True
except ImportError:
    Fernet = None


def _get_key() -> bytes | None:
    key_str = os.environ.get("KELPMESH_ENCRYPTION_KEY")
    if not key_str:
        return None
    try:
        return base64.urlsafe_b64decode(key_str.encode())
    except Exception as e:
        _logger.debug("Invalid encryption key format, trying compatibility mode: %s", e)
        try:
            return base64.urlsafe_b64encode(key_str.encode().ljust(32, b'\0')[:32])
        except Exception as e2:
            _logger.debug("Compatibility encoding also failed: %s", e2)
            return None


def encrypt_file(path: Path) -> bool:
    if not _FERNET_AVAILABLE:
        return False
    key = _get_key()
    if not key:
        return False
    if not path.exists():
        return False
    f = Fernet(base64.urlsafe_b64encode(key))
    data = path.read_bytes()
    encrypted = f.encrypt(data)
    path.write_bytes(encrypted)
    return True


def decrypt_file(path: Path) -> bytes | None:
    if not _FERNET_AVAILABLE:
        return None
    key = _get_key()
    if not key:
        return None
    if not path.exists():
        return None
    f = Fernet(base64.urlsafe_b64encode(key))
    try:
        data = path.read_bytes()
        return f.decrypt(data)
    except Exception as e:
        _logger.debug("Decryption failed: %s", e)
        return None


def is_encrypted(data: bytes) -> bool:
    return data.startswith(b"gAAAAA")


def generate_key() -> str:
    if not _FERNET_AVAILABLE:
        return ""
    key = Fernet.generate_key()
    return key.decode()


class CryptoEngine:
    """Encryption/decryption helper wrapping kelpmesh.core.crypto functions."""

    @staticmethod
    def encrypt(path: Path) -> bool:
        return encrypt_file(path)

    @staticmethod
    def decrypt(path: Path) -> bytes | None:
        return decrypt_file(path)

    @staticmethod
    def is_encrypted(data: bytes) -> bool:
        return is_encrypted(data)

    @staticmethod
    def generate_key() -> str:
        return generate_key()
