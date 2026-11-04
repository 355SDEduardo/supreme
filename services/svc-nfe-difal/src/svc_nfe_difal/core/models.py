from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any




@dataclass
class NfeProduct:
    numero: int = 0
    codigo: str = ""
    descricao: str = ""
    ncm: str = ""
    cst: str = ""
    cfop: str = ""
    quantidade: str = ""
    unidade: str = ""
    valor_unitario: str = ""
    valor_total: str = ""
    valor_icms: str = ""
    valor_bc_st: str = ""
    valor_icms_st: str = ""
    valor_bc_st_ret: str = ""
    valor_icms_st_ret: str = ""
    valor_ipi: str = ""
    valor_pis: str = ""
    valor_cofins: str = ""
    ncm_cadastrado: bool | None = None
    status_st: str = ""
    mva: str = ""
    cest: str = ""
    destinacao: str = ""


@dataclass
class NfeData:
    filename: str = ""
    numero: str = ""
    serie: str = ""
    chave: str = ""
    data_emissao: str = ""
    cnpj_emitente: str = ""
    nome_emitente: str = ""
    cnpj_destinatario: str = ""
    nome_destinatario: str = ""
    valor_total: str = ""
    valor_icms: str = ""
    valor_bc_st: str = ""
    valor_icms_st: str = ""
    valor_ipi: str = ""
    valor_pis: str = ""
    valor_cofins: str = ""
    valor_produtos: str = ""
    v_frete: str = ""
    v_seg: str = ""
    v_desc: str = ""
    v_outro: str = ""
    produtos: list[NfeProduct] = field(default_factory=list)


@dataclass(frozen=True)
class ParseIssue:
    filename: str
    message: str


@dataclass(frozen=True)
class FiscalInfo:
    status_st: str
    posicao: str = ""
    subposicao: str = ""
    item: str = ""
    mva: str = ""
    cest: str = ""


@dataclass(frozen=True)
class ComparisonItem:
    ncm: str
    posicao: str = ""
    subposicao: str = ""
    item: str = ""
    cfops: tuple[str, ...] = ()
    ncm_cadastrado: bool = False
    st: str = ""
    mva: str = ""
    cest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ncm": self.ncm,
            "posicao": self.posicao,
            "subposicao": self.subposicao,
            "item": self.item,
            "cfops": list(self.cfops),
            "ncm_cadastrado": self.ncm_cadastrado,
            "st": self.st,
            "mva": self.mva,
            "cest": self.cest,
        }


@dataclass(frozen=True)
class ComparisonSummary:
    total_ncms: int = 0
    registered_ncms: int = 0
    unregistered_ncms: int = 0


@dataclass
class ProcessingState:
    nfes: list[NfeData] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)
    comparison: list[ComparisonItem] = field(default_factory=list)
    comparison_summary: ComparisonSummary = field(default_factory=ComparisonSummary)
    logs: list[str] = field(default_factory=list)
    document_result: dict[str, Any] | None = None
    zip_comparison_result: ZipComparisonResult | None = None
    nfse_state: Any = None


@dataclass(frozen=True)
class ReconciliationNote:
    chave: str
    numero: str
    serie: str
    data_emissao: str
    cnpj_emitente: str
    nome_emitente: str
    cnpj_destinatario: str
    nome_destinatario: str
    valor_total: str
    valor_total_float: float
    valor_icms: str
    valor_icms_st: str
    filename: str


@dataclass(frozen=True)
class ReconciliationDivergence:
    chave: str
    numero: str
    serie: str
    valor_cliente: float
    valor_portal: float
    diferenca: float
    nota_cliente: ReconciliationNote
    nota_portal: ReconciliationNote
    campos_divergentes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconciliationSummary:
    total_cliente: int = 0
    total_portal: int = 0
    total_apenas_cliente: int = 0
    total_apenas_portal: int = 0
    total_comuns: int = 0
    total_divergencias: int = 0
    valor_total_cliente: float = 0.0
    valor_total_portal: float = 0.0
    valor_apenas_cliente: float = 0.0
    valor_apenas_portal: float = 0.0
    valor_comuns: float = 0.0
    totais_por_grupo: dict[str, dict[str, int | float]] = field(default_factory=dict)


@dataclass
class ZipComparisonResult:
    apenas_cliente: list[ReconciliationNote] = field(default_factory=list)
    apenas_portal: list[ReconciliationNote] = field(default_factory=list)
    em_ambos: list[ReconciliationNote] = field(default_factory=list)
    divergencias: list[ReconciliationDivergence] = field(default_factory=list)
    resumo: ReconciliationSummary = field(default_factory=ReconciliationSummary)
    issues_cliente: list[ParseIssue] = field(default_factory=list)
    issues_portal: list[ParseIssue] = field(default_factory=list)
    nome_arquivo_cliente: str = ""
    nome_arquivo_portal: str = ""
    em_ambos_portal: list[ReconciliationNote] = field(default_factory=list)
    cnpjs_empresa: list[str] = field(default_factory=list)
