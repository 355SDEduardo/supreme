from pathlib import Path
import shutil
import subprocess
import pikepdf

from svc_pdf_tools.validators.pdf_validator import check_pdf_with_qpdf


def repair_with_pikepdf(
    input_file: str | Path,
    output_file: str | Path,
    password: str | None = None,
) -> Path:
    input_path = Path(input_file)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    open_password = password or ""

    try:
        with pikepdf.open(
            input_path,
            password=open_password,
        ) as pdf:
            pdf.save(
                output_path,
                compress_streams=True,
                preserve_pdfa=True,
            )

    except pikepdf.PasswordError as exc:
        raise ValueError(
            "O PDF está protegido e a senha informada é inválida."
        ) from exc

    except pikepdf.PdfError as exc:
        raise ValueError(
            f"O arquivo não pôde ser reparado via pikepdf: {exc}"
        ) from exc

    return output_path


def repair_with_qpdf(
    input_file: str | Path,
    output_file: str | Path,
    password: str | None = None,
) -> Path:
    qpdf_bin = shutil.which("qpdf")
    if not qpdf_bin:
        raise RuntimeError("QPDF não está instalado no sistema operacional.")

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [qpdf_bin]

    if password:
        command.extend(
            [
                f"--password={password}",
                "--password-mode=bytes",
            ]
        )

    command.extend(
        [
            "--check",
            str(input_file),
            str(output_path),
        ]
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    if result.returncode not in {0, 3}:
        message = result.stderr or result.stdout
        raise RuntimeError(f"Não foi possível reparar o PDF via qpdf: {message}")

    return output_path


def repair_pdf(
    input_file: str | Path,
    output_file: str | Path,
    password: str | None = None,
) -> Path:
    input_path = Path(input_file)
    output_path = Path(output_file)

    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {input_path}")

    # Tenta pikepdf primeiro
    try:
        repair_with_pikepdf(input_path, output_path, password=password)
    except Exception:
        # Fallback para qpdf
        repair_with_qpdf(input_path, output_path, password=password)

    # Validação pós-reparo se qpdf disponível
    validation = check_pdf_with_qpdf(output_path)
    if not validation.valid and not validation.warnings and validation.return_code != 0:
        # Se pikepdf gerou o arquivo e qpdf indicou erro crítico, tenta qpdf direto
        try:
            repair_with_qpdf(input_path, output_path, password=password)
        except Exception:
            pass

    return output_path
