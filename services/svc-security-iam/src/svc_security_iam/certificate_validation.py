"""Strict PKCS#12 parsing with explicit trust anchors; no synthetic fallback."""
from datetime import datetime, timezone
from pathlib import Path
import os
import re
from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PublicFormat
from fastapi import HTTPException
from supreme_common.tax_ids import validate_cnpj, validate_cpf

def inspect_pfx_certificate(content, password):
    try:
        key, cert, intermediates = pkcs12.load_key_and_certificates(content, password.encode())
        if key is None or cert is None:
            raise ValueError('Certificado e chave privada são obrigatórios.')
        if key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo) != cert.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo):
            raise ValueError('Chave privada não corresponde ao certificado.')
        now = datetime.now(timezone.utc)
        if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
            raise ValueError('Certificado fora do período de validade.')
        names = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
        name = names[0].value if names else ''
        candidates = re.findall(r'(?<!\d)(\d{14}|\d{11})(?!\d)', name)
        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            for other in san.get_values_for_type(x509.OtherName):
                if other.type_id.dotted_string in {'2.16.76.1.3.3', '2.16.76.1.3.1'}:
                    candidates.extend(re.findall(r'\d{14}|\d{11}', other.value.decode('ascii', errors='ignore')))
        except x509.ExtensionNotFound:
            pass
        tax_id = next((c for c in candidates if (validate_cnpj(c) if len(c) == 14 else validate_cpf(c))), None)
        if not tax_id:
            raise ValueError('CNPJ/CPF válido não encontrado no certificado.')
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, 'PFX inválido, senha incorreta ou identidade/validade incompatível.') from exc
    anchor_dir = os.getenv('ICP_BRASIL_CA_DIR', '')
    if not anchor_dir or not Path(anchor_dir).is_dir():
        raise HTTPException(503, 'Configure ICP_BRASIL_CA_DIR com as raízes ICP-Brasil confiáveis.')
    anchors = []
    for path in Path(anchor_dir).glob('*.pem'):
        anchors.extend(x509.load_pem_x509_certificates(path.read_bytes()))
    chain = list(intermediates or []) + anchors
    current, visited = cert, set()
    try:
        from cryptography.hazmat.primitives import hashes
        for _ in range(10):
            fingerprint = current.fingerprint(hashes.SHA256())
            if fingerprint in visited:
                raise ValueError('Cadeia circular.')
            visited.add(fingerprint)
            if any(fingerprint == a.fingerprint(hashes.SHA256()) for a in anchors):
                break
            issuer = next((candidate for candidate in chain if candidate.subject == current.issuer), None)
            if issuer is None or not issuer.not_valid_before_utc <= now < issuer.not_valid_after_utc:
                raise ValueError('Emissor não confiável ou expirado.')
            if not issuer.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
                raise ValueError('Emissor não é autoridade certificadora.')
            current.verify_directly_issued_by(issuer)
            current = issuer
        else:
            raise ValueError('Cadeia excede o limite.')
    except Exception as exc:
        raise HTTPException(400, 'Cadeia do certificado não validada pelas raízes configuradas.') from exc
    return {'valid_from': cert.not_valid_before_utc, 'valid_until': cert.not_valid_after_utc,
            'common_name': name, 'issued_to_tax_id': tax_id, 'has_private_key': True}
