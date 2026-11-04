"""File security validation, magic numbers detection, and SHA-256 calculation."""
import hashlib
import os
from typing import Tuple

BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".vbs", ".ps1", ".msi", ".com",
    ".scr", ".jar", ".pif", ".cpl", ".reg", ".dll", ".hta"
}

ALLOWED_EXTENSIONS = {
    ".pdf", ".xml", ".jpg", ".jpeg", ".png", ".ofx", ".csv", ".xlsx", ".xls", ".zip"
}


def calculate_sha256(data: bytes) -> str:
    """Calculates standard SHA-256 hex digest."""
    return hashlib.sha256(data).hexdigest()


def validate_file_safety(filename: str, content: bytes) -> Tuple[bool, str]:
    """Validates file extension and inspects magic number signatures to block disguised executables."""
    _, ext = os.path.splitext(filename.lower())

    # 1. Block dangerous extensions
    if ext in BLOCKED_EXTENSIONS:
        return False, f"Extensão executável proibida por segurança ({ext})."

    # 2. Check allowed extension list
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Tipo de arquivo não permitido ({ext}). Permitidos: PDF, XML, OFX, CSV, Imagens, Planilhas."

    # 3. Magic Number Inspection (anti-spoofing)
    if content.startswith(b"MZ"):  # Windows PE Executable
        return False, "Arquivo executável (PE/MZ) camuflado detectado e bloqueado."

    if content.startswith(b"\x7fELF"):  # Linux ELF Executable
        return False, "Arquivo executável (ELF) camuflado detectado e bloqueado."

    if content.startswith(b"#!"):  # Shell script disguised
        return False, "Script executável camuflado detectado e bloqueado."

    # 4. Format specific checks
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            return False, "Arquivo PDF corrompido ou com assinatura de cabeçalho inválida."

    elif ext == ".xml":
        stripped = content.lstrip()
        if not (stripped.startswith(b"<?xml") or stripped.startswith(b"<")):
            return False, "Arquivo XML corrompido ou inválido."

    return True, "Arquivo válido e seguro."
