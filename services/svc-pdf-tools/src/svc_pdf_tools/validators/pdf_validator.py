from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF_SIGNATURE = b"%PDF-"


@dataclass
class PdfCheckResult:
    valid: bool
    warnings: bool
    return_code: int
    details: str


def has_pdf_signature(file_path: str | Path) -> bool:
    path = Path(file_path)
    if not path.exists() or path.is_dir():
        return False
    with path.open("rb") as file:
        header = file.read(5)
    return header == PDF_SIGNATURE


def validate_pdf(file_path: str | Path, password: str | None = None) -> None:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    if not has_pdf_signature(path):
        raise ValueError("O arquivo não possui assinatura PDF válida.")

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            if password is not None:
                decrypted = reader.decrypt(password)
                if decrypted == 0:
                    raise ValueError(f"A senha fornecida para o arquivo {path.name} é incorreta.")
            else:
                raise ValueError(f"O arquivo {path.name} está protegido por senha.")

        if len(reader.pages) == 0:
            raise ValueError("O PDF não possui páginas.")

    except PdfReadError as exc:
        raise ValueError(f"O arquivo possui estrutura PDF inválida: {exc}") from exc


def check_pdf_with_qpdf(input_file: str | Path) -> PdfCheckResult:
    qpdf_bin = shutil.which("qpdf")
    if not qpdf_bin:
        return PdfCheckResult(
            valid=True,
            warnings=False,
            return_code=0,
            details="QPDF não encontrado no sistema. Validação avançada ignorada.",
        )

    try:
        result = subprocess.run(
            [qpdf_bin, "--check", str(input_file)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        details = "\n".join(
            part for part in [result.stdout, result.stderr] if part
        ).strip()

        return PdfCheckResult(
            valid=result.returncode == 0,
            warnings=result.returncode == 3,
            return_code=result.returncode,
            details=details,
        )
    except Exception as exc:
        return PdfCheckResult(
            valid=False,
            warnings=False,
            return_code=-1,
            details=f"Erro ao executar qpdf: {exc}",
        )
