"""TOTP Multi-Factor Authentication (RFC 6238) with replay protection."""
import time
from typing import Dict, Set, Tuple
import pyotp

# Replay cache: maps user_id -> set of (token, time_step)
_used_tokens_cache: Dict[str, Set[Tuple[str, int]]] = {}


def generate_totp_secret() -> str:
    """Generate base32 secret for TOTP."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, user_email: str, issuer_name: str = "PortalContabil") -> str:
    """Generate otpauth:// URI for QR code pairing."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=user_email, issuer_name=issuer_name)


def verify_totp_token(secret: str, token: str, user_id: str) -> Tuple[bool, str]:
    """Verify 6-digit TOTP token with +/- 1 time step tolerance (valid window of 30 seconds)
    and enforce replay protection.
    """
    totp = pyotp.TOTP(secret)
    current_time = time.time()
    current_step = int(current_time // 30)

    # Check +/- 1 cycle (valid_window=1)
    is_valid = totp.verify(token, valid_window=1)
    if not is_valid:
        return False, "Código TOTP inválido ou expirado."

    # Enforce Replay Protection: Token cannot be reused within the same time window
    user_used = _used_tokens_cache.setdefault(user_id, set())

    # Purge old steps older than 2 steps
    old_steps = {s for (t, s) in user_used if current_step - s > 2}
    user_used = {(t, s) for (t, s) in user_used if s not in old_steps}
    _used_tokens_cache[user_id] = user_used

    # Check if (token, step) already used
    for (used_token, used_step) in user_used:
        if used_token == token and abs(current_step - used_step) <= 1:
            return False, "Código TOTP já utilizado neste ciclo temporal (proteção contra replay)."

    user_used.add((token, current_step))
    return True, "MFA validado com sucesso."
