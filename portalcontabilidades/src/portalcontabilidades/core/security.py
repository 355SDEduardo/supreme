"""Security, password hashing, and JWT tokens."""
import hashlib
import hmac
import os
import base64
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from portalcontabilidades.core.config import settings


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations and salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return base64.b64encode(salt + key).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against salted PBKDF2 hash."""
    try:
        decoded = base64.b64decode(hashed_password.encode("ascii"))
        salt = decoded[:16]
        expected_key = decoded[16:]
        key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100000)
        return hmac.compare_digest(key, expected_key)
    except Exception:
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (4 - (len(data) % 4)) if (len(data) % 4) != 0 else ""
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"iat": int(now.timestamp()), "exp": int(expire.timestamp())})
    
    header = {"alg": settings.ALGORITHM, "typ": "JWT"}
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(to_encode, separators=(",", ":")).encode("utf-8")
    
    encoded_header = _b64url_encode(header_bytes)
    encoded_payload = _b64url_encode(payload_bytes)
    
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    encoded_signature = _b64url_encode(signature)
    
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a JWT token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        encoded_header, encoded_payload, encoded_signature = parts
        
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(encoded_signature)
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        
        payload_bytes = _b64url_decode(encoded_payload)
        payload = json.loads(payload_bytes.decode("utf-8"))
        
        # Check expiration
        exp = payload.get("exp")
        if exp and exp < time.time():
            return None
            
        return payload
    except Exception:
        return None
