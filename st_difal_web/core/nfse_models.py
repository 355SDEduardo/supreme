from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {f.name: serialize(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    return value


class Serializable:
    def to_dict(self) -> dict[str, Any]:
        return serialize(self)


class NfseFamily(str, Enum):
    """Família de origem do documento XML."""
    NATIONAL = "NATIONAL"              # Padrão Nacional (Portal Nacional ADN/RTC)
    ABRASF_1 = "ABRASF_1"              # ABRASF v1.00
    ABRASF_2 = "ABRASF_2"              # ABRASF v2.00 a v2.04
    PAULISTANA = "PAULISTANA"          # Prefeitura de São Paulo
    DSF = "DSF"                        # Provedor DSF
    BETHA = "BETHA"                    # Provedor Betha Sistemas
    ISSNET = "ISSNET"                  # Provedor ISS.Net
    GINFES = "GINFES"                  # Provedor Ginfes
    IPM = "IPM"                        # Provedor IPM
    OUTROS = "OUTROS"                  # Provedor local/legado não catalogado

class DocumentKind(str, Enum):
    """Classificação do artefato XML processado."""
    NFSE = "NFSE"                      # NFS-e Autorizada (documento fiscal)
    DPS = "DPS"                        # Declaração de Prestação de Serviços avulsa
    EVENT = "EVENT"                    # Evento fiscal (cancelamento, substituição, etc.)
    RESPONSE = "RESPONSE"              # Envelope/resposta de webservice
    UNKNOWN = "UNKNOWN"                # Artefato não identificável

class DocumentStatus(str, Enum):
    """Status projetado do documento fiscal."""
    AUTHORIZED = "AUTHORIZED"          # Autorizada e vigente
    CANCELLED = "CANCELLED"            # Cancelada formalmente
    SUBSTITUTED = "SUBSTITUTED"        # Substituída por outra NFS-e
    REJECTED = "REJECTED"              # Rejeitada
    UNKNOWN = "UNKNOWN"

class IssWithholdingType(str, Enum):
    """Tratamento de tpRetISSQN da NFS-e Nacional."""
    RETIDO_TOMADOR = "2"
    RETIDO_INTERMEDIARIO = "3"
    NAO_RETIDO = "1"
    NAO_INFORMADO = "NAO_INFORMADO"

class FindingSeverity(str, Enum):
    """Gravidade do apontamento de auditoria fiscal/contábil."""
    CRITICAL = "CRITICAL"              # Erro invalidante / risco tributário grave
    HIGH = "HIGH"                      # Divergência substancial de valores ou alíquotas
    WARNING = "WARNING"                # Inconsistência cadastral ou alerta de conformidade
    INFO = "INFO"                      # Nota informativa de auditoria



@dataclass(frozen=True)
class NfseIdentity(Serializable):
    access_key: str                   # Chave normalizada (50 dígitos no nacional, sem prefixo 'NFS')
    xml_id: str                       # Identificador exatamente como consta no atributo Id do XML
    nfse_number: str                  # Número oficial da NFS-e
    series: str                       # Série da NFS-e
    dps_number: str = ""              # Número da DPS vinculada/encapsulada
    dps_series: str = ""              # Série da DPS vinculada
    competence_date: date | None = None # Data de competência (fato gerador)
    nfse_issued_at: datetime | None = None # Data/hora de autorização/processamento (dhProc)
    dps_issued_at: datetime | None = None  # Data/hora de emissão declarada na DPS (dhEmi)


@dataclass(frozen=True)
class NfseParty(Serializable):
    tax_id: str                       # CNPJ ou CPF (formato alfanumérico ou numérico preservado)
    name: str                         # Razão Social / Nome completo
    trade_name: str = ""              # Nome Fantasia
    municipal_tax_id: str = ""        # Inscrição Municipal
    ibge_city_code: str = ""          # Código IBGE do município (7 dígitos)
    city_name: str = ""               # Nome do município
    state_code: str = ""              # UF (2 caracteres)
    is_simple_national: bool | None = None # Indicador de optante do Simples Nacional
    is_mei: bool | None = None        # Indicador de MEI
    tax_regime: str = ""              # Regime Especial de Tributação declarado


@dataclass(frozen=True)
class NfseServiceItem(Serializable):
    item_index: int = 1
    national_tax_code: str = ""       # Código de Tributação Nacional (cTribNac do Padrão Nacional)
    lc116_subitem: str = ""           # Subitem LC 116/2003 (ex: "07.02", "14.01")
    municipal_tax_code: str = ""      # Código de tributação específico do município
    nbs_code: str = ""                # Nomenclatura Brasileira de Serviços
    description: str = ""             # Discriminação dos serviços
    gross_amount: Decimal = Decimal("0.00") # Valor bruto do item
    execution_city_ibge: str = ""     # Município onde o serviço foi executado
    incidence_city_ibge: str = ""     # Município de incidência tributária do ISS declarado


@dataclass(frozen=True)
class NfseAmounts(Serializable):
    gross_service: Decimal            # Valor bruto dos serviços (vServ)
    unconditional_discount: Decimal = Decimal("0.00") # Desconto incondicionado (vDescIncond)
    conditional_discount: Decimal = Decimal("0.00")   # Desconto condicionado (vDescCond)
    deductions: Decimal = Decimal("0.00")             # Deduções legais da base de cálculo
    iss_base: Decimal = Decimal("0.00")               # Base de cálculo do ISS (vBC)
    iss_rate_declared: Decimal | None = None          # Alíquota informada na DPS
    iss_rate_applied: Decimal | None = None           # Alíquota aplicada pelo ambiente (pAliqAplic)
    iss_amount: Decimal = Decimal("0.00")             # Valor do ISS apurado (vISSQN)
    iss_withheld_amount: Decimal = Decimal("0.00")    # Valor do ISS efetivamente retido
    total_withheld: Decimal = Decimal("0.00")         # Total de retenções (vTotalRet)
    net_amount_declared: Decimal = Decimal("0.00")    # Valor líquido informado no XML (vLiq)
    net_amount_calculated: Decimal = Decimal("0.00")  # Valor líquido recalculado pela regra auditada
    net_difference: Decimal = Decimal("0.00")         # Diferença entre declarado e auditado


@dataclass(frozen=True)
class NfseFederalWithholding(Serializable):
    irrf: Decimal = Decimal("0.00")           # Imposto de Renda Retido na Fonte (vRetIRRF)
    inss_cp: Decimal = Decimal("0.00")         # Contribuição Previdenciária / INSS (vRetCP)
    csll: Decimal = Decimal("0.00")            # CSLL Retida (vRetCSLL)
    pis: Decimal = Decimal("0.00")             # PIS Retido (vPis)
    cofins: Decimal = Decimal("0.00")          # COFINS Retida (vCofins)
    other_withholdings: Decimal = Decimal("0.00") # Outras retenções municipais/federais
    social_contributions_total: Decimal | None = None  # NT007: vRetCSLL é total de contribuições sociais
    pis_own: Decimal = Decimal("0.00")
    cofins_own: Decimal = Decimal("0.00")
    social_retention_type: str = ""


@dataclass(frozen=True)
class NfseIbsCbs(Serializable):
    layout_version: str = ""                   # Versão do layout RTC (ex.: "v1.01")
    cst: str = ""                              # Código de Situação Tributária IBS/CBS
    c_class_trib: str = ""                     # Código de Classificação Tributária
    ind_op: str = ""                           # Indicador da Operação
    tax_base: Decimal = Decimal("0.00")        # Base de cálculo de IBS/CBS
    ibs_state_rate: Decimal = Decimal("0.00")  # Alíquota estadual IBS
    ibs_state_amount: Decimal = Decimal("0.00")# Valor IBS estadual
    ibs_city_rate: Decimal = Decimal("0.00")   # Alíquota municipal IBS
    ibs_city_amount: Decimal = Decimal("0.00") # Valor IBS municipal
    cbs_rate: Decimal = Decimal("0.00")        # Alíquota CBS federal
    cbs_amount: Decimal = Decimal("0.00")      # Valor CBS federal
    total_ibs: Decimal = Decimal("0.00")       # Totalizador IBS
    total_cbs: Decimal = Decimal("0.00")       # Totalizador CBS
    total_nf: Decimal = Decimal("0.00")        # Total geral da nota sob RTC
    ibs_state_effective_rate: Decimal | None = None
    ibs_city_effective_rate: Decimal | None = None
    cbs_effective_rate: Decimal | None = None
    has_complex_adjustments: bool = False


@dataclass(frozen=True)
class NfseProvenance(Serializable):
    canonical_field: str       # Nome do campo canônico (ex.: "amounts.iss_base")
    source_xpath: str          # XPath original no XML (ex.: "/NFSe/infNFSe/valores/vBC")
    raw_value: str             # String bruta extraída
    normalized_value: str      # Valor normalizado
    source_schema: str         # Schema id utilizado
    transformation_rule: str   # Regra aplicada (ex.: "to_decimal", "strip_prefix")


@dataclass(frozen=True)
class NfseFinding(Serializable):
    code: str                  # Código da regra (ex.: "ISS_RETENTION_RATE_MISMATCH")
    severity: FindingSeverity  # CRITICAL, HIGH, WARNING, INFO
    title: str                 # Resumo do apontamento
    description: str           # Explicação detalhada da divergência
    expected: str              # Valor esperado pela regra fiscal
    reported: str              # Valor reportado no documento
    difference: Decimal = Decimal("0.00") # Diferença numérica (quando aplicável)
    legal_basis: str = ""      # Fundamentação legal (ex.: "LC 116/2003, Art. 3º; CGSN 140")
    source_fields: tuple[str, ...] = ()   # Tags/campos de origem envolvidos


@dataclass(frozen=True)
class CanonicalNfse(Serializable):
    artifact_sha256: str                        # Hash SHA-256 do arquivo original
    filename: str                               # Nome do arquivo de upload
    family: NfseFamily                          # Família do schema detectado
    kind: DocumentKind                          # Tipo de artefato
    status: DocumentStatus                      # Status projetado (AUTHORIZED, CANCELLED, etc.)
    identity: NfseIdentity
    issuer: NfseParty | None                    # Emissor da NFS-e (órgão gerador/município)
    provider: NfseParty                         # Prestador do serviço (prest na DPS)
    customer: NfseParty | None                  # Tomador do serviço
    intermediary: NfseParty | None              # Intermediário (se houver)
    services: tuple[NfseServiceItem, ...]       # Lista de serviços
    amounts: NfseAmounts                        # Totais monetários e ISS
    federal_withholding: NfseFederalWithholding # Retenções federais
    iss_withholding_type: IssWithholdingType    # tpRetISSQN interpretado
    ibs_cbs: NfseIbsCbs | None                  # Grupo RTC / Reforma Tributária
    provenance: tuple[NfseProvenance, ...] = () # Trilha de proveniência dos campos
    findings: tuple[NfseFinding, ...] = ()       # Apontamentos fiscais detectados


@dataclass(frozen=True)
class NfseEvent(Serializable):
    event_id: str                      # Identificador único do evento
    target_access_key: str             # Chave da NFS-e afetada
    event_type: str                    # CANCELAMENTO, SUBSTITUICAO, MANIFESTACAO, etc.
    sequence_number: int               # Número sequencial do evento
    event_datetime: datetime           # Data e hora do registro do evento
    reason: str                        # Motivo / justificativa
    author_tax_id: str                 # CNPJ/CPF do autor do evento
    substituting_access_key: str = ""  # Chave da nota substituta (quando aplicável)
    raw_payload_sha256: str = ""       # SHA-256 do XML do evento
    target_number: str = ""
    target_city_ibge: str = ""
    target_provider_tax_id: str = ""
    confirmed: bool = True


@dataclass
class NfseProcessingState(Serializable):
    documents: list[CanonicalNfse] = field(default_factory=list)
    events: list[NfseEvent] = field(default_factory=list)
    orphan_events: list[NfseEvent] = field(default_factory=list)
    total_processed: int = 0
    total_valid: int = 0
    total_with_findings: int = 0
    total_gross_amount: Decimal = Decimal("0.00")
    total_iss_amount: Decimal = Decimal("0.00")
    total_withheld_amount: Decimal = Decimal("0.00")
    total_net_amount: Decimal = Decimal("0.00")
    issues: list[dict[str, str]] = field(default_factory=list) # Erros graves de arquivo
    logs: list[str] = field(default_factory=list)
    total_iss_withheld: Decimal = Decimal("0.00")
    total_federal_withheld: Decimal = Decimal("0.00")
    original_artifacts: dict[str, bytes] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {f.name: serialize(getattr(self, f.name)) for f in fields(self)
                if f.name != "original_artifacts"}
