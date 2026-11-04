from __future__ import annotations

import xml.etree.ElementTree as ET

from svc_nfe_difal.core.models import NfeData, NfeProduct


class NfeParser:
    NAMESPACES = {"ns": "http://www.portalfiscal.inf.br/nfe"}

    def parse_bytes(self, content: bytes, filename: str) -> NfeData:
        if not content.strip():
            raise ValueError("O arquivo XML está vazio.")
        # Remover NULs permite detectar declarações também em UTF-16/UTF-32.
        upper_content = content.replace(b"\x00", b"").upper()
        if b"<!DOCTYPE" in upper_content or b"<!ENTITY" in upper_content:
            raise ValueError("XML com DTD ou entidade não é aceito.")

        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ValueError("O arquivo não contém um XML bem-formado.") from exc
        data = self._extract_data(root)
        data.filename = filename
        return data

    def _extract_data(self, root: ET.Element) -> NfeData:
        produtos = self._extract_products(root)
        return NfeData(
            numero=self._get_tag(root, ".//ns:infNFe/ns:ide/ns:nNF"),
            serie=(
                self._get_tag(root, ".//ns:infNFe/ns:ide/ns:serie")
                or self._get_tag(root, ".//ns:infNFe/ns:ide/ns:nSeries")
            ),
            chave=(
                self._get_tag(root, ".//ns:infNFeSuplementar/ns:chNFe")
                or self._get_tag(root, ".//ns:protNFe/ns:infProt/ns:chNFe")
                or self._key_from_inf_nfe(root)
            ),
            data_emissao=self._get_tag(root, ".//ns:infNFe/ns:ide/ns:dhEmi"),
            cnpj_emitente=self._get_tag(root, ".//ns:infNFe/ns:emit/ns:CNPJ"),
            nome_emitente=self._get_tag(root, ".//ns:infNFe/ns:emit/ns:xNome"),
            cnpj_destinatario=(
                self._get_tag(root, ".//ns:infNFe/ns:dest/ns:CNPJ")
                or self._get_tag(root, ".//ns:infNFe/ns:dest/ns:CPF")
            ),
            nome_destinatario=self._get_tag(root, ".//ns:infNFe/ns:dest/ns:xNome"),
            valor_total=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vNF"),
            valor_icms=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vICMS"),
            valor_bc_st=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vBCST"),
            valor_icms_st=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vST"),
            valor_ipi=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vIPI"),
            valor_pis=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vPIS"),
            valor_cofins=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vCOFINS"),
            valor_produtos=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vProd"),
            v_frete=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vFrete"),
            v_seg=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vSeg"),
            v_desc=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vDesc"),
            v_outro=self._get_tag(root, ".//ns:infNFe/ns:total/ns:ICMSTot/ns:vOutro"),
            produtos=produtos,
        )

    def _extract_products(self, root: ET.Element) -> list[NfeProduct]:
        nodes = root.findall(".//ns:det", self.NAMESPACES)
        if not nodes:
            nodes = [node for node in root.iter() if self._local_name(node) == "det"]

        products: list[NfeProduct] = []
        for index, node in enumerate(nodes, start=1):
            cst = (
                self._get_tag(node, ".//ns:imposto/ns:ICMS/*/ns:CST")
                or self._get_tag(node, ".//ns:imposto/ns:ICMS/*/ns:CSOSN")
                or self._find_tax_text(node, "ICMS", ("CST", "CSOSN"))
            )
            products.append(
                NfeProduct(
                    numero=index,
                    codigo=self._get_tag(node, ".//ns:cProd"),
                    descricao=self._get_tag(node, ".//ns:xProd"),
                    ncm=self._get_tag(node, ".//ns:NCM"),
                    cst=cst,
                    cfop=self._get_tag(node, ".//ns:CFOP"),
                    quantidade=self._get_tag(node, ".//ns:qCom"),
                    unidade=self._get_tag(node, ".//ns:uCom"),
                    valor_unitario=self._get_tag(node, ".//ns:vUnCom"),
                    valor_total=self._get_tag(node, ".//ns:vProd"),
                    valor_icms=self._get_tag(node, ".//ns:imposto/ns:ICMS/*/ns:vICMS"),
                    valor_bc_st=self._get_tag(node, ".//ns:imposto/ns:ICMS/*/ns:vBCST"),
                    valor_icms_st=(
                        self._get_tag(node, ".//ns:imposto/ns:ICMS/*/ns:vICMSST")
                        or self._get_tag(node, ".//ns:imposto/ns:ICMS/*/ns:vST")
                    ),
                    valor_bc_st_ret=self._get_tag(node, ".//ns:imposto/ns:ICMS/*/ns:vBCSTRet"),
                    valor_icms_st_ret=self._get_tag(node, ".//ns:imposto/ns:ICMS/*/ns:vICMSSTRet"),
                    valor_ipi=self._find_tax_text(node, "IPI", ("vIPI",)),
                    valor_pis=self._find_tax_text(node, "PIS", ("vPIS",)),
                    valor_cofins=self._find_tax_text(node, "COFINS", ("vCOFINS",)),
                )
            )
        return products

    def _get_tag(self, root: ET.Element, path: str) -> str:
        element = root.find(path, self.NAMESPACES)
        if element is not None and element.text:
            return element.text.strip()

        clean_path = "/".join(
            part.split(":")[-1] for part in path.replace(".//", "").split("/")
        )
        try:
            element = root.find(f".//{clean_path}")
        except SyntaxError:
            element = None
        if element is not None and element.text:
            return element.text.strip()
        return ""

    def _find_tax_text(
        self, root: ET.Element, tax_name: str, value_names: tuple[str, ...]
    ) -> str:
        for tax_node in root.iter():
            if self._local_name(tax_node) != tax_name:
                continue
            for node in tax_node.iter():
                if self._local_name(node) in value_names and node.text and node.text.strip():
                    return node.text.strip()
        return ""

    def _key_from_inf_nfe(self, root: ET.Element) -> str:
        for node in root.iter():
            if self._local_name(node) != "infNFe":
                continue
            identifier = node.attrib.get("Id", "")
            return identifier.removeprefix("NFe")
        return ""

    @staticmethod
    def _local_name(element: ET.Element) -> str:
        return str(element.tag).split("}")[-1]
