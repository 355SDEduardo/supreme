"""Unit and Integration Tests for Feature 10: Segurança, LGPD e Certificados Digitais."""


import pytest
from datetime import datetime, timedelta, timezone
import pyotp

from svc_security_iam.models import AuditLog, DigitalCertificate, PrivacyConsent, LgpdSubjectRequest
from svc_security_iam.crypto_vault import (
    encrypt_payload, decrypt_payload, encrypt_string, decrypt_string, calculate_expiration_status
)
from svc_security_iam.mfa_totp import (
    generate_totp_secret, verify_totp_token
)
from svc_security_iam.audit_logger import (
    record_audit_log, query_audit_logs, sanitize_payload
)
from svc_security_iam.lgpd_service import (
    record_consent, create_subject_request
)


def test_aes_gcm_vault_encryption():
    """Validates AES-256-GCM encryption and decryption roundtrip."""
    original_data = b"Certificado Digital A1 Conteudo Binario Super Secreto"
    encrypted = encrypt_payload(original_data)
    assert encrypted != original_data
    assert len(encrypted) > len(original_data)

    decrypted = decrypt_payload(encrypted)
    assert decrypted == original_data

    # String roundtrip
    pwd = "MinhaSenhaForteCertificado123!"
    enc_pwd = encrypt_string(pwd)
    dec_pwd = decrypt_string(enc_pwd)
    assert dec_pwd == pwd


def test_totp_generation_and_replay_prevention():
    """Validates TOTP RFC 6238 generation and rejection of token reuse in same window."""
    secret = generate_totp_secret()
    totp = pyotp.TOTP(secret)
    token = totp.now()

    # First validation must succeed
    valid, msg = verify_totp_token(secret, token, "user-test-123")
    assert valid is True
    assert "sucesso" in msg.lower()

    # Replay attempt with same token for same user must be rejected
    valid_replay, msg_replay = verify_totp_token(secret, token, "user-test-123")
    assert valid_replay is False
    assert "replay" in msg_replay.lower()

    # Invalid token check
    valid_invalid, _ = verify_totp_token(secret, "000000", "user-test-123")
    assert valid_invalid is False


def test_audit_log_append_only_immutability(db_session):
    """Validates that audit_logs are strictly append-only and block updates/deletions."""
    log = record_audit_log(
        db=db_session,
        action="view_bank_statement",
        resource_type="bank_account",
        resource_id="acc-001",
        ip_address="192.168.1.100",
        actor_user_id="user-456",
        payload_snapshot={"sensitive_account": "12345-6"}
    )
    assert log.id is not None

    # Attempting to update must raise PermissionError
    log.action = "tampered_action"
    with pytest.raises(PermissionError):
        db_session.commit()

    db_session.rollback()

    # Attempting to delete must raise PermissionError
    fresh_log = db_session.query(AuditLog).filter(AuditLog.id == log.id).first()
    db_session.delete(fresh_log)
    with pytest.raises(PermissionError):
        db_session.commit()


def test_sensitive_payload_sanitization():
    """Ensures passwords and secrets are never stored in plain text in audit logs."""
    raw = {
        "user": "contabil@exemplo.com",
        "password": "SecretPassword123",
        "nested": {"token": "jwt-token-val", "action": "ok"}
    }
    sanitized = sanitize_payload(raw)
    assert sanitized["password"] == "********"
    assert sanitized["nested"]["token"] == "********"
    assert sanitized["user"] == "contabil@exemplo.com"


def test_certificate_expiration_alert_rules():
    """Validates proactive alerts at 30, 15, 7, 1 days and expired status."""
    now = datetime.now(timezone.utc)

    # 25 days left -> 30_days alert level
    st, days, warn = calculate_expiration_status(now + timedelta(days=25))
    assert st == "active"
    assert warn == "30_days"

    # 12 days left -> 15_days alert level
    st, days, warn = calculate_expiration_status(now + timedelta(days=12))
    assert st == "active"
    assert warn == "15_days"

    # 5 days left -> 7_days alert level
    st, days, warn = calculate_expiration_status(now + timedelta(days=5))
    assert st == "active"
    assert warn == "7_days"

    # 1 day left -> 1_day alert level
    st, days, warn = calculate_expiration_status(now + timedelta(hours=20))
    assert st == "active"
    assert warn == "1_day"

    # Expired
    st, days, warn = calculate_expiration_status(now - timedelta(days=2))
    assert st == "expired"
    assert warn == "expired"


def test_lgpd_consents_and_requests(db_session):
    """Validates LGPD consent registration and Art. 18 data subject requests."""
    consent = record_consent(
        db=db_session,
        user_id="user-lgpd-01",
        term_version="v2026.1",
        ip_address="200.150.10.5",
        legal_basis="Execucao de Contrato"
    )
    assert consent.id is not None
    assert consent.term_version == "v2026.1"

    req = create_subject_request(
        db=db_session,
        user_id="user-lgpd-01",
        request_type="access",
        details="Solicitacao de relatorio de dados cadastrais e fiscais"
    )
    assert req.id is not None
    assert req.status == "pending"
