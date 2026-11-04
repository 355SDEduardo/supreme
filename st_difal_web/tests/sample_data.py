SAMPLE_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe35210000000000000000550010000000011000000001">
      <ide><nNF>12345</nNF><serie>1</serie><dhEmi>2026-08-01T10:00:00-03:00</dhEmi></ide>
      <emit><CNPJ>12345678000195</CNPJ><xNome>EMPRESA TESTE LTDA</xNome></emit>
      <dest><CNPJ>98765432000110</CNPJ><xNome>CLIENTE TESTE SA</xNome></dest>
      <det nItem="1">
        <prod>
          <cProd>=FORMULA</cProd><xProd>PRODUTO TESTE</xProd><NCM>21069090</NCM>
          <CFOP>6102</CFOP><uCom>UN</uCom><qCom>2.0000</qCom><vUnCom>10.5000</vUnCom><vProd>21.00</vProd>
        </prod>
        <imposto>
          <ICMS><ICMS10><CST>10</CST><vICMS>3.78</vICMS><vBCST>30.00</vBCST><vICMSST>5.00</vICMSST></ICMS10></ICMS>
          <IPI><IPITrib><CST>50</CST><vIPI>1.00</vIPI></IPITrib></IPI>
          <PIS><PISAliq><vPIS>0.30</vPIS></PISAliq></PIS>
          <COFINS><COFINSAliq><vCOFINS>1.40</vCOFINS></COFINSAliq></COFINS>
        </imposto>
      </det>
      <total><ICMSTot><vProd>21.00</vProd><vICMS>3.78</vICMS><vBCST>30.00</vBCST><vST>5.00</vST><vIPI>1.00</vIPI><vPIS>0.30</vPIS><vCOFINS>1.40</vCOFINS><vNF>26.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
  <protNFe><infProt><chNFe>35210000000000000000550010000000011000000001</chNFe></infProt></protNFe>
</nfeProc>"""


def fiscal_record(ncm: str = "21069090") -> dict[str, str]:
    return {
        "NCM": ncm,
        "Posição": "Preparações alimentícias",
        "Subposição": "Outras",
        "Subitem": "Outras",
        "Estado": "DF",
        "Alíquota Interna": "20%",
        "Base Reduzida": "Não se aplica",
        "Diferimento": "Não se aplica",
        "FCP": "Não se aplica",
        "Isenção": "Consultar",
        "Não Incidência": "Não se aplica",
        "ST": "Sim",
        "MVA": "40%",
        "CEST": "1234567",
        "Suspensão": "Não se aplica",
    }
