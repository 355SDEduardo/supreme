"""
Parser avançado para NFS-e Padrão Nacional (RFB / SPED).
Conforme instrucoes para skill parser.md:
- Gestão resiliente de namespaces com fallback para local-name()
- Modelagem contábil estrita com Decimal
- Regex especializado para xInfComp (PIX, Dados Bancários, Deduções, Contratos)
- Reconciliação financeira e integridade contábil automática
"""

import re
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from typing import Optional, Tuple, Dict, Any
from lxml import etree

from svc_nfse_engine.models import (
    NFSNacionalModel,
    Participante,
    Endereco,
    TributacaoFederal,
    DadosComplementaresExtraidos,
    AuditoriaContabil,
)


class NFSeNacionalParser:
    """Parser para NFSe Padrão Nacional (RFB / SPED)."""

    NS = {
        "nfe": "http://www.sped.fazenda.gov.br/nfse",
        "ds": "http://www.w3.org/2000/09/xmldsig#",
    }

    # Regex patterns para campos em xInfComp
    REGEX_PIX_CHAVE = re.compile(
        r"(?:PIX|CHAVE\s*PIX|CHAVE)(?:\s+PARA\s+O\s+[A-Za-z0-9]+)?[\s:=]+([a-zA-Z0-9_\-\.\@\+]{8,60})",
        re.IGNORECASE,
    )
    REGEX_BANCO = re.compile(
        r"(?:BANCO|BCO)[:\s]+([A-Za-z0-9\s\-]+?)(?=[,;\n]|AG|AGENCIA|CONTA|C\/C|$)",
        re.IGNORECASE,
    )
    REGEX_AGENCIA = re.compile(
        r"(?:AG|AG[EÊ]NCIA)[:\s]*([0-9]{3,5}(?:-[0-9X])?)",
        re.IGNORECASE,
    )
    REGEX_CONTA = re.compile(
        r"(?:CONTA(?:\s*CORRENTE)?|C\/C)[:\s]*([0-9]{4,12}(?:-[0-9X])?)",
        re.IGNORECASE,
    )
    REGEX_CONTRATO = re.compile(
        r"(?:CONTRATO|CTR|CT)[:\s#]*([A-Za-z0-9\/\.\-]+)",
        re.IGNORECASE,
    )
    REGEX_PEDIDO = re.compile(
        r"(?:PEDIDO|PO|ORDEM\s*DE\s*COMPRA|OC|PEDIDO\s*DE\s*COMPRA)[:\s#]*([A-Za-z0-9\/\.\-]+)",
        re.IGNORECASE,
    )
    REGEX_MEDICAO = re.compile(
        r"(?:MEDI[CÇ][AÃ]O|MED)[:\s#]*([A-Za-z0-9\/\.\-]+)",
        re.IGNORECASE,
    )
    REGEX_DEDUC_VT = re.compile(
        r"(?:VALE(?:\s*|-)?TRANSPORTE|VT)[:\s]*R?\$?\s*([0-9\.\,]+)",
        re.IGNORECASE,
    )
    REGEX_DEDUC_VR = re.compile(
        r"(?:VALE(?:\s*|-)?(?:REFEI[CÇ][AÃ]O|ALIMENTA[CÇ][AÃ]O)|VR|VA)[:\s]*R?\$?\s*([0-9\.\,]+)",
        re.IGNORECASE,
    )
    REGEX_DEDUC_MAT = re.compile(
        r"(?:MATERIAL|MATERIAIS)[:\s]*R?\$?\s*([0-9\.\,]+)",
        re.IGNORECASE,
    )

    @classmethod
    def _text(
        cls,
        node: Optional[etree._Element],
        xpath: str,
        default: Optional[str] = None,
    ) -> Optional[str]:
        if node is None:
            return default
        try:
            elements = node.xpath(xpath, namespaces=cls.NS)
            if elements and elements[0].text is not None:
                val = elements[0].text.strip()
                return val if val else default
        except Exception:
            pass

        # Fallback local-name se o seletor com prefixo não retornar
        try:
            clean_tag = xpath.split(":")[-1].split("/")[-1].split("@")[-1]
            if "@" in xpath:
                attr_name = xpath.split("@")[-1]
                val = node.get(attr_name)
                if val:
                    return val.strip()
            fallback_query = f".//*[local-name()='{clean_tag}']"
            fallbacks = node.xpath(fallback_query)
            if fallbacks and fallbacks[0].text is not None:
                val = fallbacks[0].text.strip()
                return val if val else default
        except Exception:
            pass

        return default

    @classmethod
    def _decimal(
        cls,
        node: Optional[etree._Element],
        xpath: str,
        default: str = "0.00",
    ) -> Decimal:
        raw = cls._text(node, xpath, default)
        if raw is None:
            return Decimal(default)
        try:
            # Substitui vírgula por ponto se necessário
            clean = raw.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".") if "," in raw and "." in raw else raw.replace(",", ".")
            return Decimal(clean).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return Decimal(default)

    @classmethod
    def _int(
        cls,
        node: Optional[etree._Element],
        xpath: str,
        default: int = 0,
    ) -> int:
        raw = cls._text(node, xpath)
        if raw is None:
            return default
        try:
            digits = "".join(filter(str.isdigit, raw))
            return int(digits) if digits else default
        except Exception:
            return default

    @classmethod
    def _parse_datetime(cls, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            # Fallback para formatos comuns
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(raw[:19], fmt)
                except Exception:
                    pass
        return None

    @classmethod
    def _parse_date(cls, raw: Optional[str]) -> Optional[date]:
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except Exception:
            try:
                dt = cls._parse_datetime(raw)
                return dt.date() if dt else None
            except Exception:
                pass
        return None

    @classmethod
    def extract_xinfcomp_data(cls, x_inf_comp: Optional[str]) -> DadosComplementaresExtraidos:
        """Extrai dados não estruturados contidos em Informações Complementares."""
        if not x_inf_comp:
            return DadosComplementaresExtraidos()

        extraidos = DadosComplementaresExtraidos(outras_observacoes=x_inf_comp)

        # 1. PIX
        pix_match = cls.REGEX_PIX_CHAVE.search(x_inf_comp)
        if pix_match:
            chave = pix_match.group(1).strip().rstrip(".,;:()")
            extraidos.chave_pix = chave
            if "@" in chave:
                extraidos.tipo_pix = "E-MAIL"
            elif len("".join(filter(str.isdigit, chave))) == 14:
                extraidos.tipo_pix = "CNPJ"
            elif len("".join(filter(str.isdigit, chave))) == 11:
                extraidos.tipo_pix = "CPF"
            elif "+" in chave or (chave.startswith("55") and len(chave) in (12, 13)):
                extraidos.tipo_pix = "TELEFONE"
            else:
                extraidos.tipo_pix = "CHAVE ALEATÓRIA / EVP"

        # 2. Dados Bancários
        banco_match = cls.REGEX_BANCO.search(x_inf_comp)
        if banco_match:
            extraidos.banco_nome = banco_match.group(1).strip()

        ag_match = cls.REGEX_AGENCIA.search(x_inf_comp)
        if ag_match:
            extraidos.agencia = ag_match.group(1).strip()

        cc_match = cls.REGEX_CONTA.search(x_inf_comp)
        if cc_match:
            extraidos.conta_corrente = cc_match.group(1).strip()

        # 3. Contratos e Pedidos
        ctr_match = cls.REGEX_CONTRATO.search(x_inf_comp)
        if ctr_match:
            extraidos.numero_contrato = ctr_match.group(1).strip().rstrip(".,;:()")

        ped_match = cls.REGEX_PEDIDO.search(x_inf_comp)
        if ped_match:
            extraidos.numero_pedido = ped_match.group(1).strip().rstrip(".,;:()")

        med_match = cls.REGEX_MEDICAO.search(x_inf_comp)
        if med_match:
            extraidos.numero_medicao = med_match.group(1).strip().rstrip(".,;:()")

        # 4. Deduções informadas
        vt_match = cls.REGEX_DEDUC_VT.search(x_inf_comp)
        if vt_match:
            try:
                v = vt_match.group(1).replace(".", "").replace(",", ".")
                extraidos.deducao_vt = Decimal(v).quantize(Decimal("0.01"))
            except Exception:
                pass

        vr_match = cls.REGEX_DEDUC_VR.search(x_inf_comp)
        if vr_match:
            try:
                v = vr_match.group(1).replace(".", "").replace(",", ".")
                extraidos.deducao_vr = Decimal(v).quantize(Decimal("0.01"))
            except Exception:
                pass

        mat_match = cls.REGEX_DEDUC_MAT.search(x_inf_comp)
        if mat_match:
            try:
                v = mat_match.group(1).replace(".", "").replace(",", ".")
                extraidos.deducao_material = Decimal(v).quantize(Decimal("0.01"))
            except Exception:
                pass

        return extraidos

    @classmethod
    def audit_reconciliation(
        cls,
        valor_servico: Decimal,
        valor_liquido: Decimal,
        valor_total_retencoes: Decimal,
        valor_issqn: Decimal,
        tipo_retencao_issqn: int,
        valor_ret_cp_inss: Decimal,
        valor_pis: Decimal,
        tp_retencao_pis_cofins: int,
        valor_cofins: Decimal,
        valor_ret_irrf: Decimal,
        valor_ret_csll: Decimal,
    ) -> AuditoriaContabil:
        """
        Executa a reconciliação financeira e verificação de integridade contábil:
        1. vLiq == vServ - vTotalRet
        2. vTotalRet == (ISS retido + INSS retido + PIS retido + COFINS retido + IRRF + CSLL)
        """
        detalhes: list[str] = []

        # 1. Checagem vLiq = vServ - vTotalRet
        liq_esperado = (valor_servico - valor_total_retencoes).quantize(Decimal("0.01"))
        dif_liq = (valor_liquido - liq_esperado).quantize(Decimal("0.01"))
        eq_liq_valida = abs(dif_liq) <= Decimal("0.05")  # tolerância de arredondamento

        if not eq_liq_valida:
            detalhes.append(
                f"Divergência de Líquido: Declarado R$ {valor_liquido:.2f} != Calculado (vServ R$ {valor_servico:.2f} - vTotalRet R$ {valor_total_retencoes:.2f} = R$ {liq_esperado:.2f}). Dif: R$ {dif_liq:.2f}"
            )
        else:
            detalhes.append("Equação de Valor Líquido (vLiq = vServ - vTotalRet) 100% conciliada.")

        # 2. Composição do vTotalRet
        iss_retido = valor_issqn if tipo_retencao_issqn == 2 else Decimal("0.00")
        pis_retido = valor_pis if tp_retencao_pis_cofins in (1, 2) else Decimal("0.00")
        cofins_retido = valor_cofins if tp_retencao_pis_cofins in (1, 2) else Decimal("0.00")

        total_retencoes_calc = (
            iss_retido + valor_ret_cp_inss + pis_retido + cofins_retido + valor_ret_irrf + valor_ret_csll
        ).quantize(Decimal("0.01"))

        dif_ret = (valor_total_retencoes - total_retencoes_calc).quantize(Decimal("0.01"))
        soma_ret_valida = abs(dif_ret) <= Decimal("0.05")

        if not soma_ret_valida:
            detalhes.append(
                f"Divergência na soma de Retenções: Declarado R$ {valor_total_retencoes:.2f} vs Soma calculada R$ {total_retencoes_calc:.2f} (ISS Retido: R$ {iss_retido:.2f}, INSS: R$ {valor_ret_cp_inss:.2f}, Federais: R$ {(pis_retido+cofins_retido):.2f}). Dif: R$ {dif_ret:.2f}"
            )
        else:
            if valor_total_retencoes > Decimal("0.00"):
                detalhes.append(
                    f"Soma das retenções na fonte conciliada: R$ {valor_total_retencoes:.2f} (ISS: R$ {iss_retido:.2f}, INSS: R$ {valor_ret_cp_inss:.2f})."
                )
            else:
                detalhes.append("Operação sem retenções na fonte.")

        status = "CONCILIADO"
        if not eq_liq_valida or not soma_ret_valida:
            status = "INCONSISTENTE" if abs(dif_liq) > Decimal("1.00") or abs(dif_ret) > Decimal("1.00") else "ALERTA"

        return AuditoriaContabil(
            equacao_liquido_valida=eq_liq_valida,
            diferenca_liquido=dif_liq,
            soma_retencoes_valida=soma_ret_valida,
            diferenca_retencoes=dif_ret,
            iss_retido_esperado=iss_retido,
            total_retencoes_calculado=total_retencoes_calc,
            status_conciliacao=status,
            detalhes_auditoria=detalhes,
        )

    @classmethod
    def parse(
        cls,
        xml_content: bytes | str,
        filename: Optional[str] = None,
    ) -> NFSNacionalModel:
        """
        Executa o parsing completo de um XML da NFS-e Nacional (versao 1.01).
        """
        if isinstance(xml_content, str):
            xml_bytes = xml_content.encode("utf-8")
        else:
            xml_bytes = xml_content

        # Remoção de eventual BOM UTF-8
        if xml_bytes.startswith(b"\xef\xbb\xbf"):
            xml_bytes = xml_bytes[3:]

        # Parser com suporte a recuperação de XML levemente mal formatado
        parser = etree.XMLParser(recover=True, remove_blank_text=True)
        root = etree.fromstring(xml_bytes, parser=parser)

        # 1. Localização do nó infNFSe (com ou sem namespace)
        inf_nfse = root.find("nfe:infNFSe", namespaces=cls.NS)
        if inf_nfse is None:
            # Fallback sem namespace
            inf_nfse_nodes = root.xpath("//*[local-name()='infNFSe']")
            if not inf_nfse_nodes:
                raise ValueError("Nó raiz 'infNFSe' não foi localizado no documento XML.")
            inf_nfse = inf_nfse_nodes[0]

        # 2. Localização do nó infDPS
        dps = inf_nfse.find(".//nfe:infDPS", namespaces=cls.NS)
        if dps is None:
            dps_nodes = inf_nfse.xpath(".//*[local-name()='infDPS']")
            if not dps_nodes:
                dps_nodes = root.xpath("//*[local-name()='infDPS']")
            if not dps_nodes:
                raise ValueError("Nó 'infDPS' não foi localizado no documento XML.")
            dps = dps_nodes[0]

        # 3. Emitente
        emit_node = inf_nfse.find("nfe:emit", namespaces=cls.NS)
        if emit_node is None:
            emit_nodes = inf_nfse.xpath(".//*[local-name()='emit']")
            emit_node = emit_nodes[0] if emit_nodes else None

        ender_emit = None
        if emit_node is not None:
            ender_emit = emit_node.find("nfe:enderNac", namespaces=cls.NS)
            if ender_emit is None:
                ender_nodes = emit_node.xpath(".//*[local-name()='enderNac']")
                ender_emit = ender_nodes[0] if ender_nodes else None

        emitente = Participante(
            cnpj=cls._text(emit_node, "nfe:CNPJ") or cls._text(emit_node, "CNPJ") or "",
            cpf=cls._text(emit_node, "nfe:CPF") or cls._text(emit_node, "CPF"),
            razao_social=cls._text(emit_node, "nfe:xNome") or cls._text(emit_node, "xNome"),
            nome_fantasia=cls._text(emit_node, "nfe:xFant") or cls._text(emit_node, "xFant"),
            telefone=cls._text(emit_node, "nfe:fone") or cls._text(emit_node, "fone"),
            email=cls._text(emit_node, "nfe:email") or cls._text(emit_node, "email"),
            endereco=Endereco(
                logradouro=cls._text(ender_emit, "nfe:xLgr") or cls._text(ender_emit, "xLgr") or "",
                numero=cls._text(ender_emit, "nfe:nro") or cls._text(ender_emit, "nro") or "",
                bairro=cls._text(ender_emit, "nfe:xBairro") or cls._text(ender_emit, "xBairro") or "",
                codigo_municipio=cls._text(ender_emit, "nfe:cMun") or cls._text(ender_emit, "cMun") or "",
                cep=cls._text(ender_emit, "nfe:CEP") or cls._text(ender_emit, "CEP") or "",
                uf=cls._text(ender_emit, "nfe:UF") or cls._text(ender_emit, "UF"),
                complemento=cls._text(ender_emit, "nfe:xCpl") or cls._text(ender_emit, "xCpl"),
            )
            if ender_emit is not None
            else None,
        )

        # 4. Tomador
        toma_node = dps.find("nfe:toma", namespaces=cls.NS)
        if toma_node is None:
            toma_nodes = dps.xpath(".//*[local-name()='toma']")
            toma_node = toma_nodes[0] if toma_nodes else None

        end_toma = None
        end_nac_toma = None
        if toma_node is not None:
            end_toma = toma_node.find("nfe:end", namespaces=cls.NS)
            if end_toma is None:
                end_nodes = toma_node.xpath(".//*[local-name()='end']")
                end_toma = end_nodes[0] if end_nodes else None

            if end_toma is not None:
                end_nac_toma = end_toma.find("nfe:endNac", namespaces=cls.NS)
                if end_nac_toma is None:
                    nac_nodes = end_toma.xpath(".//*[local-name()='endNac']")
                    end_nac_toma = nac_nodes[0] if nac_nodes else None

        tomador = Participante(
            cnpj=cls._text(toma_node, "nfe:CNPJ") or cls._text(toma_node, "CNPJ") or "",
            cpf=cls._text(toma_node, "nfe:CPF") or cls._text(toma_node, "CPF"),
            razao_social=cls._text(toma_node, "nfe:xNome") or cls._text(toma_node, "xNome"),
            telefone=cls._text(toma_node, "nfe:fone") or cls._text(toma_node, "fone"),
            email=cls._text(toma_node, "nfe:email") or cls._text(toma_node, "email"),
            endereco=Endereco(
                logradouro=cls._text(end_toma, "nfe:xLgr") or cls._text(end_toma, "xLgr") or "",
                numero=cls._text(end_toma, "nfe:nro") or cls._text(end_toma, "nro") or "",
                bairro=cls._text(end_toma, "nfe:xBairro") or cls._text(end_toma, "xBairro") or "",
                codigo_municipio=cls._text(end_nac_toma, "nfe:cMun")
                or cls._text(end_nac_toma, "cMun")
                or cls._text(end_toma, "nfe:cMun")
                or "",
                cep=cls._text(end_nac_toma, "nfe:CEP")
                or cls._text(end_nac_toma, "CEP")
                or cls._text(end_toma, "nfe:CEP")
                or "",
                uf=cls._text(end_toma, "nfe:UF") or cls._text(end_toma, "UF"),
                complemento=cls._text(end_toma, "nfe:xCpl") or cls._text(end_toma, "xCpl"),
            )
            if end_toma is not None
            else None,
        )

        # 5. Tributos Federais
        trib_fed_node = dps.find(".//nfe:tribFed", namespaces=cls.NS)
        if trib_fed_node is None:
            trib_fed_nodes = dps.xpath(".//*[local-name()='tribFed']")
            trib_fed_node = trib_fed_nodes[0] if trib_fed_nodes else None

        piscofins_node = None
        if trib_fed_node is not None:
            piscofins_node = trib_fed_node.find("nfe:piscofins", namespaces=cls.NS)
            if piscofins_node is None:
                pc_nodes = trib_fed_node.xpath(".//*[local-name()='piscofins']")
                piscofins_node = pc_nodes[0] if pc_nodes else None

        tributos_federais = TributacaoFederal(
            cst=cls._text(piscofins_node, "nfe:CST") or cls._text(piscofins_node, "CST") or "",
            base_calculo=cls._decimal(piscofins_node, "nfe:vBCPisCofins")
            if piscofins_node is not None
            else Decimal("0.00"),
            aliq_pis=cls._decimal(piscofins_node, "nfe:pAliqPis")
            if piscofins_node is not None
            else Decimal("0.00"),
            aliq_cofins=cls._decimal(piscofins_node, "nfe:pAliqCofins")
            if piscofins_node is not None
            else Decimal("0.00"),
            valor_pis=cls._decimal(piscofins_node, "nfe:vPis")
            if piscofins_node is not None
            else Decimal("0.00"),
            valor_cofins=cls._decimal(piscofins_node, "nfe:vCofins")
            if piscofins_node is not None
            else Decimal("0.00"),
            tp_retencao_pis_cofins=cls._int(piscofins_node, "nfe:tpRetPisCofins")
            if piscofins_node is not None
            else 0,
            valor_ret_cp_inss=cls._decimal(trib_fed_node, "nfe:vRetCP", default="0.00")
            if trib_fed_node is not None
            else Decimal("0.00"),
            valor_ret_irrf=cls._decimal(trib_fed_node, "nfe:vRetIRRF", default="0.00")
            if trib_fed_node is not None
            else Decimal("0.00"),
            valor_ret_csll=cls._decimal(trib_fed_node, "nfe:vRetCSLL", default="0.00")
            if trib_fed_node is not None
            else Decimal("0.00"),
        )

        # 6. Assinatura Digital
        sig_node = root.find("ds:Signature", namespaces=cls.NS)
        if sig_node is None:
            sig_nodes = root.xpath("//*[local-name()='Signature']")
            sig_node = sig_nodes[0] if sig_nodes else None

        digest = cls._text(sig_node, ".//ds:DigestValue") or cls._text(sig_node, ".//*[local-name()='DigestValue']") or ""
        signature_val = cls._text(sig_node, ".//ds:SignatureValue") or cls._text(sig_node, ".//*[local-name()='SignatureValue']") or ""

        # 7. Dados da DPS e Serviços
        id_dps = dps.get("Id") or cls._text(dps, "@Id") or ""
        serie_dps = cls._text(dps, "nfe:serie") or cls._text(dps, "serie") or ""
        n_dps = cls._int(dps, "nfe:nDPS") or cls._int(dps, "nDPS")

        dh_emi_str = cls._text(dps, "nfe:dhEmi") or cls._text(dps, "dhEmi")
        dh_emi = cls._parse_datetime(dh_emi_str) or datetime.now()

        d_compet_str = cls._text(dps, "nfe:dCompet") or cls._text(dps, "dCompet")
        d_compet = cls._parse_date(d_compet_str) or dh_emi.date()

        c_trib_nac = cls._text(dps, ".//nfe:cTribNac") or cls._text(dps, ".//*[local-name()='cTribNac']") or ""
        c_nbs = cls._text(dps, ".//nfe:cNBS") or cls._text(dps, ".//*[local-name()='cNBS']")
        desc_serv = cls._text(dps, ".//nfe:xDescServ") or cls._text(dps, ".//*[local-name()='xDescServ']") or ""
        inf_comp = cls._text(dps, ".//nfe:xInfComp") or cls._text(dps, ".//*[local-name()='xInfComp']")

        op_simp_nac = cls._int(dps, ".//nfe:opSimpNac") or cls._int(dps, ".//*[local-name()='opSimpNac']") or 1
        reg_esp_trib = cls._int(dps, ".//nfe:regEspTrib") or cls._int(dps, ".//*[local-name()='regEspTrib']")

        # 8. Valores da NFS-e
        v_serv = cls._decimal(dps, ".//nfe:vServPrest/nfe:vServ") or cls._decimal(dps, ".//*[local-name()='vServ']")
        valores_node = inf_nfse.find("nfe:valores", namespaces=cls.NS)
        if valores_node is None:
            val_nodes = inf_nfse.xpath(".//*[local-name()='valores']")
            valores_node = val_nodes[0] if val_nodes else None

        v_bc = cls._decimal(valores_node, "nfe:vBC") or cls._decimal(valores_node, "vBC") or v_serv
        p_aliq = cls._decimal(valores_node, "nfe:pAliqAplic") or cls._decimal(valores_node, "pAliqAplic")
        if p_aliq == Decimal("0.00"):
            p_aliq = cls._decimal(dps, ".//nfe:tribMun/nfe:pAliq") or cls._decimal(dps, ".//*[local-name()='pAliq']")

        v_issqn = cls._decimal(valores_node, "nfe:vISSQN") or cls._decimal(valores_node, "vISSQN")
        tp_ret_issqn = cls._int(dps, ".//nfe:tpRetISSQN") or cls._int(dps, ".//*[local-name()='tpRetISSQN']") or 1
        trib_issqn = cls._int(dps, ".//nfe:tribISSQN") or cls._int(dps, ".//*[local-name()='tribISSQN']") or 1

        v_total_ret = cls._decimal(valores_node, "nfe:vTotalRet", default="0.00") or cls._decimal(valores_node, "vTotalRet", default="0.00")
        v_liq = cls._decimal(valores_node, "nfe:vLiq") or cls._decimal(valores_node, "vLiq")
        if v_liq == Decimal("0.00"):
            v_liq = (v_serv - v_total_ret).quantize(Decimal("0.01"))

        # Cargas tributárias aproximadas
        p_tot_trib_fed = cls._decimal(dps, ".//nfe:pTotTribFed") or cls._decimal(dps, ".//*[local-name()='pTotTribFed']")
        p_tot_trib_est = cls._decimal(dps, ".//nfe:pTotTribEst") or cls._decimal(dps, ".//*[local-name()='pTotTribEst']")
        p_tot_trib_mun = cls._decimal(dps, ".//nfe:pTotTribMun") or cls._decimal(dps, ".//*[local-name()='pTotTribMun']")

        # 9. Dados de Controle da infNFSe
        chave_nfse = inf_nfse.get("Id") or cls._text(inf_nfse, "@Id") or ""
        n_nfse = cls._int(inf_nfse, "nfe:nNFSe") or cls._int(inf_nfse, "nNFSe")
        n_dfse = cls._int(inf_nfse, "nfe:nDFSe") or cls._int(inf_nfse, "nDFSe")
        status_code = cls._int(inf_nfse, "nfe:cStat") or cls._int(inf_nfse, "cStat") or 100

        dh_proc_str = cls._text(inf_nfse, "nfe:dhProc") or cls._text(inf_nfse, "dhProc")
        dh_proc = cls._parse_datetime(dh_proc_str) or dh_emi

        ver_aplic = cls._text(inf_nfse, "nfe:verAplic") or cls._text(inf_nfse, "verAplic") or ""
        versao_leiaute = root.get("versao") or inf_nfse.get("versao") or "1.01"
        amb_ger = cls._int(inf_nfse, "nfe:ambGer") or cls._int(inf_nfse, "ambGer") or 1
        tp_emis = cls._int(inf_nfse, "nfe:tpEmis") or cls._int(inf_nfse, "tpEmis") or 1
        proc_emi = cls._int(inf_nfse, "nfe:procEmi") or cls._int(inf_nfse, "procEmi") or 1

        loc_emi = cls._text(inf_nfse, "nfe:xLocEmi") or cls._text(inf_nfse, "xLocEmi") or ""
        loc_prest = cls._text(inf_nfse, "nfe:xLocPrestacao") or cls._text(inf_nfse, "xLocPrestacao") or ""
        c_loc_incid = cls._text(inf_nfse, "nfe:cLocIncid") or cls._text(inf_nfse, "cLocIncid") or ""
        loc_incid = cls._text(inf_nfse, "nfe:xLocIncid") or cls._text(inf_nfse, "xLocIncid") or ""
        x_trib_nac = cls._text(inf_nfse, "nfe:xTribNac") or cls._text(inf_nfse, "xTribNac") or ""
        x_nbs = cls._text(inf_nfse, "nfe:xNBS") or cls._text(inf_nfse, "xNBS")

        # 10. Inteligência Contábil: Extração Regex de xInfComp
        dados_comp = cls.extract_xinfcomp_data(inf_comp)

        # 11. Reconciliação Contábil & Auditoria
        auditoria = cls.audit_reconciliation(
            valor_servico=v_serv,
            valor_liquido=v_liq,
            valor_total_retencoes=v_total_ret,
            valor_issqn=v_issqn,
            tipo_retencao_issqn=tp_ret_issqn,
            valor_ret_cp_inss=tributos_federais.valor_ret_cp_inss,
            valor_pis=tributos_federais.valor_pis,
            tp_retencao_pis_cofins=tributos_federais.tp_retencao_pis_cofins,
            valor_cofins=tributos_federais.valor_cofins,
            valor_ret_irrf=tributos_federais.valor_ret_irrf,
            valor_ret_csll=tributos_federais.valor_ret_csll,
        )

        return NFSNacionalModel(
            chave_nfse=chave_nfse,
            numero_nfse=n_nfse,
            numero_dfse=n_dfse,
            status=status_code,
            data_hora_processamento=dh_proc,
            versao_aplicativo=ver_aplic,
            versao_leiaute=versao_leiaute,
            ambiente_gerador=amb_ger,
            tipo_emissao=tp_emis,
            processo_emissao=proc_emi,
            local_emissao=loc_emi,
            local_prestacao=loc_prest,
            codigo_municipio_incidencia=c_loc_incid,
            local_incidencia=loc_incid,
            tributacao_nacional_desc=x_trib_nac,
            nbs_desc=x_nbs,
            emitente=emitente,
            tomador=tomador,
            id_dps=id_dps,
            serie_dps=serie_dps,
            numero_dps=n_dps,
            data_emissao_dps=dh_emi,
            data_competencia=d_compet,
            codigo_tributacao_nacional=c_trib_nac,
            codigo_nbs=c_nbs,
            descricao_servico=desc_serv,
            informacoes_complementares=inf_comp,
            optante_simples_nacional=op_simp_nac,
            regime_especial_tributacao=reg_esp_trib,
            valor_servico=v_serv,
            base_calculo=v_bc,
            aliquota_aplicada=p_aliq,
            valor_issqn=v_issqn,
            tipo_retencao_issqn=tp_ret_issqn,
            tributacao_issqn=trib_issqn,
            valor_total_retencoes=v_total_ret,
            valor_liquido=v_liq,
            tributos_federais=tributos_federais,
            perc_trib_federal=p_tot_trib_fed,
            perc_trib_estadual=p_tot_trib_est,
            perc_trib_municipal=p_tot_trib_mun,
            digest_value=digest,
            signature_value=signature_val,
            dados_complementares_extraidos=dados_comp,
            auditoria=auditoria,
            arquivo_origem=filename,
        )
