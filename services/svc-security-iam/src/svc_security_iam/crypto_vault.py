"""Cryptographic vault for Digital Certificates (A1) and sensitive data using AES-256-GCM."""
import os
import re
from datetime import datetime, timezone
from typing import Tuple, Dict, Any, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography import x509
from svc_security_iam.config import settings


def _get_aes_key() -> bytes:
    key_hex = settings.MASTER_ENCRYPTION_KEY
    key_bytes = bytes.fromhex(key_hex)
    if len(key_bytes) != 32:
        raise ValueError("MASTER_ENCRYPTION_KEY must be a 32-byte (64 hex characters) key.")
    return key_bytes


def encrypt_payload(data: bytes) -> bytes:
    """Encrypt binary payload using AES-256-GCM.
    Returns: nonce (12 bytes) + ciphertext + tag (16 bytes)."""
    key = _get_aes_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext


def decrypt_payload(encrypted_data: bytes) -> bytes:
    """Decrypt binary payload using AES-256-GCM."""
    key = _get_aes_key()
    aesgcm = AESGCM(key)
    if len(encrypted_data) < 28:
        raise ValueError("Encrypted data is too short to contain nonce and authentication tag.")
    nonce = encrypted_data[:12]
    ciphertext = encrypted_data[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)


def encrypt_string(text: str) -> str:
    """Encrypt string to hex representation."""
    encrypted_bytes = encrypt_payload(text.encode("utf-8"))
    return encrypted_bytes.hex()


def decrypt_string(encrypted_hex: str) -> str:
    """Decrypt hex string to original text."""
    encrypted_bytes = bytes.fromhex(encrypted_hex)
    return decrypt_payload(encrypted_bytes).decode("utf-8")


def inspect_pfx_certificate(pfx_data, password):
    from .certificate_validation import inspect_pfx_certificate as inspect
    return inspect(pfx_data, password)


def calculate_expiration_status(valid_until: datetime) -> Tuple[str, int, Optional[str]]:
    """Determine status ('active', 'expired'), remaining days, and warning alert level (30, 15, 7, 1 days)."""
    now = datetime.now(timezone.utc)
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
        
    diff = valid_until - now
    days_left = diff.days
    
    if days_left < 0:
        return "expired", days_left, "expired"
        
    warning_level = None
    if days_left <= 1:
        warning_level = "1_day"
    elif days_left <= 7:
        warning_level = "7_days"
    elif days_left <= 15:
        warning_level = "15_days"
    elif days_left <= 30:
        warning_level = "30_days"
        
    return "active", days_left, warning_level
