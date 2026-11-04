"""Pre-transmission XML Schema and mandatory fields validator."""
import xml.etree.ElementTree as ET
from typing import Tuple, Optional


def validate_fiscal_xml(system_target: str, event_type: str, xml_content: str) -> Tuple[bool, Optional[str]]:
    """Validates XML syntax and mandatory legal elements according to official government schemas (eSocial S-1.3, EFD-Reinf, NFS-e)."""
    if not xml_content or not xml_content.strip():
        return False, "Conteúdo XML vazio."

    # 1. XML Well-formedness check
    try:
        root = ET.fromstring(xml_content.strip())
    except ET.ParseError as e:
        return False, f"Erro de sintaxe XML: {str(e)}"

    xml_text = xml_content.lower()

    # 2. eSocial Validation
    if system_target == "esocial":
        if "ideempregador" not in xml_text or "nrinsc" not in xml_text:
            return False, "eSocial: Elemento obrigatório <ideEmpregador> ou <nrInsc> ausente no XML."

        if event_type.upper() == "S-1200":
            if "idetrabalhador" not in xml_text or "cpftrab" not in xml_text:
                return False, "eSocial S-1200: Ausência obrigatória do elemento <ideTrabalhador> / <cpfTrab>."

        elif event_type.upper() == "S-1299":
            if "iderespinf" not in xml_text and "inffech" not in xml_text:
                return False, "eSocial S-1299: Evento de fechamento deve conter informações do fechamento/responsável."

    # 3. EFD-Reinf Validation
    elif system_target == "efd_reinf":
        if "idecontri" not in xml_text or "nrinsc" not in xml_text:
            return False, "EFD-Reinf: Elemento obrigatório <ideContri> ou <nrInsc> ausente."

        if event_type.upper() == "R-4020":
            if "idebenef" not in xml_text:
                return False, "EFD-Reinf R-4020: Obrigatória identificação do beneficiário do rendimento (<ideBenef>)."

    # 4. NFS-e Nacional Validation
    elif system_target == "nfse_nacional":
        if "infdps" not in xml_text or "cnpj" not in xml_text:
            return False, "NFS-e Nacional: DPS deve conter o bloco <infDPS> e o CNPJ do prestador."

    return True, None
