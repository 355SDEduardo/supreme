"""
Modelos de dados para NFS-e Padrão Nacional (RFB / SPED versao 1.01).
Utiliza Pydantic v2 para validação rigorosa, tipagem contábil (Decimal) e serialização JSON.
"""

from decimal import Decimal
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_serializer, computed_field


class Endereco(BaseModel):
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    codigo_municipio: str = ""
    cep: str = ""
    uf: Optional[str] = None
    complemento: Optional[str] = None

    @computed_field
    @property
    def endereco_completo(self) -> str:
        parts = [f"{self.logradouro}, {self.numero}".strip(", ")]
        if self.complemento:
            parts.append(self.complemento)
        if self.bairro:
            parts.append(self.bairro)
        if self.codigo_municipio:
            parts.append(f"IBGE {self.codigo_municipio}")
        if self.uf:
            parts.append(self.uf)
        if self.cep:
            parts.append(f"CEP {self.cep}")
        return " - ".join([p for p in parts if p])


class Participante(BaseModel):
    cnpj: str = ""
    cpf: Optional[str] = None
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    endereco: Optional[Endereco] = None
    telefone: Optional[str] = None
    email: Optional[str] = None

    @computed_field
    @property
    def documento_formatado(self) -> str:
        doc = self.cnpj or self.cpf or ""
        doc_digits = "".join(filter(str.isdigit, doc))
        if len(doc_digits) == 14:
            return f"{doc_digits[:2]}.{doc_digits[2:5]}.{doc_digits[5:8]}/{doc_digits[8:12]}-{doc_digits[12:]}"
        elif len(doc_digits) == 11:
            return f"{doc_digits[:3]}.{doc_digits[3:6]}.{doc_digits[6:9]}-{doc_digits[9:]}"
        return doc


class TributacaoFederal(BaseModel):
    cst: str = ""
    base_calculo: Decimal = Decimal("0.00")
    aliq_pis: Decimal = Decimal("0.00")
    aliq_cofins: Decimal = Decimal("0.00")
    valor_pis: Decimal = Decimal("0.00")
    valor_cofins: Decimal = Decimal("0.00")
    tp_retencao_pis_cofins: int = 0  # 0=Não, 1=Sim, 2=Retido
    valor_ret_cp_inss: Decimal = Decimal("0.00")
    valor_ret_irrf: Decimal = Decimal("0.00")
    valor_ret_csll: Decimal = Decimal("0.00")

    @field_serializer(
        "base_calculo",
        "aliq_pis",
        "aliq_cofins",
        "valor_pis",
        "valor_cofins",
        "valor_ret_cp_inss",
        "valor_ret_irrf",
        "valor_ret_csll",
    )
    def serialize_decimal(self, v: Decimal) -> float:
        return float(v)


class DadosComplementaresExtraidos(BaseModel):
    chave_pix: Optional[str] = None
    tipo_pix: Optional[str] = None  # CNPJ, CPF, EMAIL, TELEFONE, ALEATORIA
    banco_nome: Optional[str] = None
    banco_codigo: Optional[str] = None
    agencia: Optional[str] = None
    conta_corrente: Optional[str] = None
    numero_contrato: Optional[str] = None
    numero_pedido: Optional[str] = None
    numero_medicao: Optional[str] = None
    deducao_vt: Optional[Decimal] = None
    deducao_vr: Optional[Decimal] = None
    deducao_material: Optional[Decimal] = None
    outras_observacoes: Optional[str] = None

    @field_serializer("deducao_vt", "deducao_vr", "deducao_material")
    def serialize_decimal(self, v: Optional[Decimal]) -> Optional[float]:
        return float(v) if v is not None else None


class AuditoriaContabil(BaseModel):
    equacao_liquido_valida: bool = True
    diferenca_liquido: Decimal = Decimal("0.00")
    soma_retencoes_valida: bool = True
    diferenca_retencoes: Decimal = Decimal("0.00")
    iss_retido_esperado: Decimal = Decimal("0.00")
    total_retencoes_calculado: Decimal = Decimal("0.00")
    status_conciliacao: str = "CONCILIADO"  # CONCILIADO, ALERTA, INCONSISTENTE
    detalhes_auditoria: List[str] = Field(default_factory=list)

    @field_serializer(
        "diferenca_liquido",
        "diferenca_retencoes",
        "iss_retido_esperado",
        "total_retencoes_calculado",
    )
    def serialize_decimal(self, v: Decimal) -> float:
        return float(v)


class NFSNacionalModel(BaseModel):
    # Identificação e Cabeçalho
    chave_nfse: str
    numero_nfse: int
    numero_dfse: int = 0
    status: int = 100  # 100 = Autorizado
    data_hora_processamento: datetime
    versao_aplicativo: str = ""
    versao_leiaute: str = "1.01"
    ambiente_gerador: int = 1  # 1=Produção, 2=Homologação
    tipo_emissao: int = 1      # 1=Normal
    processo_emissao: int = 1  # 1=Aplicativo do Contribuinte, 2=Web

    # Localidades
    local_emissao: str = ""
    local_prestacao: str = ""
    codigo_municipio_incidencia: str = ""
    local_incidencia: str = ""
    tributacao_nacional_desc: str = ""
    nbs_desc: Optional[str] = None

    # Participantes
    emitente: Participante
    tomador: Participante

    # DPS (Origem)
    id_dps: str = ""
    serie_dps: str = ""
    numero_dps: int = 0
    data_emissao_dps: datetime
    data_competencia: date
    codigo_tributacao_nacional: str = ""
    codigo_nbs: Optional[str] = None
    descricao_servico: str = ""
    informacoes_complementares: Optional[str] = None
    optante_simples_nacional: int = 1  # 1=Não Optante, 2=Optante
    regime_especial_tributacao: int = 0

    # Valores e Tributos Consolidados
    valor_servico: Decimal = Decimal("0.00")
    base_calculo: Decimal = Decimal("0.00")
    aliquota_aplicada: Decimal = Decimal("0.00")
    valor_issqn: Decimal = Decimal("0.00")
    tipo_retencao_issqn: int = 1  # 1=Não Retido (Prestador recolhe), 2=Retido pelo Tomador
    tributacao_issqn: int = 1     # 1=Exigível
    valor_total_retencoes: Decimal = Decimal("0.00")
    valor_liquido: Decimal = Decimal("0.00")

    # Tributos Federais
    tributos_federais: TributacaoFederal

    # Carga Tributária Aproximada (Lei da Transparência / IBPT)
    perc_trib_federal: Decimal = Decimal("0.00")
    perc_trib_estadual: Decimal = Decimal("0.00")
    perc_trib_municipal: Decimal = Decimal("0.00")

    # Assinatura Digital
    digest_value: str = ""
    signature_value: str = ""

    # Inteligência de Negócio & Extrações Avançadas
    dados_complementares_extraidos: DadosComplementaresExtraidos = Field(
        default_factory=DadosComplementaresExtraidos
    )
    auditoria: AuditoriaContabil = Field(default_factory=AuditoriaContabil)

    # Metadados de processamento
    arquivo_origem: Optional[str] = None
    data_processamento_sistema: datetime = Field(default_factory=datetime.now)

    @field_serializer(
        "valor_servico",
        "base_calculo",
        "aliquota_aplicada",
        "valor_issqn",
        "valor_total_retencoes",
        "valor_liquido",
        "perc_trib_federal",
        "perc_trib_estadual",
        "perc_trib_municipal",
    )
    def serialize_decimal(self, v: Decimal) -> float:
        return float(v)

    @field_serializer("data_hora_processamento", "data_emissao_dps", "data_processamento_sistema")
    def serialize_datetime(self, v: datetime) -> str:
        return v.isoformat()

    @field_serializer("data_competencia")
    def serialize_date(self, v: date) -> str:
        return v.isoformat()

    @computed_field
    @property
    def status_descricao(self) -> str:
        return "Autorizada" if self.status == 100 else f"Status {self.status}"

    @computed_field
    @property
    def iss_retido_pelo_tomador(self) -> bool:
        return self.tipo_retencao_issqn == 2

    @computed_field
    @property
    def optante_simples_descricao(self) -> str:
        if self.optante_simples_nacional == 1:
            return "Não Optante"
        elif self.optante_simples_nacional == 2:
            return "Optante - ME / EPP"
        return f"Código {self.optante_simples_nacional}"
