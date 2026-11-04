"""
Gerador de XMLs de amostra fiéis aos casos documentados em 'instrucoes para skill parser.md'.
Casos cobertos:
- Doc 1: Com retenção de ISS (R$ 438,71) e retenção de INSS (R$ 722,34), vTotalRet = R$ 1.161,05.
- Doc 16: Sem retenção na fonte (vTotalRet ausente/zero), regime Simples Nacional.
- Doc 18: Com retenção ISS (R$ 271,33) e INSS (R$ 474,83), vTotalRet = R$ 746,16 e xCpl no tomador.
- Doc 20: Sem código NBS (cNBS) e sem descrição NBS (xNBS).
- Doc 25: Serviço de Consultoria em TI com chave PIX CNPJ e dados de contrato em xInfComp.
"""

from pathlib import Path
from typing import List, Dict

SAMPLE_DOC_1 = """<?xml version="1.0" encoding="UTF-8"?>
<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">
  <infNFSe Id="NFS31470062410100000000000000000000000000000000000001">
    <xLocEmi>Paracatu</xLocEmi>
    <xLocPrestacao>Paracatu</xLocPrestacao>
    <nNFSe>1001</nNFSe>
    <cLocIncid>3147006</cLocIncid>
    <xLocIncid>Paracatu</xLocIncid>
    <xTribNac>Cessao de mao-de-obra e servicos terceirizados</xTribNac>
    <xNBS>Servicos de apoio a gestao de edificios</xNBS>
    <verAplic>EmissorWeb_1.5.0.0</verAplic>
    <ambGer>1</ambGer>
    <tpEmis>1</tpEmis>
    <procEmi>2</procEmi>
    <cStat>100</cStat>
    <dhProc>2026-01-15T14:28:10-03:00</dhProc>
    <nDFSe>584920</nDFSe>
    <emit>
      <CNPJ>12345678000199</CNPJ>
      <xNome>CONSERVA SERVICOS E FACILIDADES LTDA</xNome>
      <enderNac>
        <xLgr>Avenida Central</xLgr>
        <nro>500</nro>
        <xBairro>Centro</xBairro>
        <cMun>3147006</cMun>
        <UF>MG</UF>
        <CEP>38600000</CEP>
      </enderNac>
      <fone>3836719000</fone>
      <email>fiscal@conserva.com.br</email>
    </emit>
    <valores>
      <vBC>8774.20</vBC>
      <pAliqAplic>5.00</pAliqAplic>
      <vISSQN>438.71</vISSQN>
      <vTotalRet>1161.05</vTotalRet>
      <vLiq>7613.15</vLiq>
    </valores>
    <DPS versao="1.01">
      <infDPS Id="DPS31470062410100000000000000000000000000000000000001">
        <tpAmb>1</tpAmb>
        <dhEmi>2026-01-15T14:15:00-03:00</dhEmi>
        <verAplic>EmissorWeb_1.4.0.26</verAplic>
        <serie>900</serie>
        <nDPS>1001</nDPS>
        <dCompet>2026-01-15</dCompet>
        <tpEmit>1</tpEmit>
        <cLocEmi>3147006</cLocEmi>
        <prest>
          <CNPJ>12345678000199</CNPJ>
          <regTrib>
            <opSimpNac>1</opSimpNac>
            <regEspTrib>0</regEspTrib>
          </regTrib>
        </prest>
        <toma>
          <CNPJ>98765432000110</CNPJ>
          <xNome>MINERACAO OURO VERDE S.A.</xNome>
          <end>
            <endNac>
              <cMun>3147006</cMun>
              <CEP>38600100</CEP>
            </endNac>
            <xLgr>Rodovia MG 188</xLgr>
            <nro>KM 15</nro>
            <xBairro>Zona Rural</xBairro>
          </end>
        </toma>
        <serv>
          <locPrest>
            <cLocPrestacao>3147006</cLocPrestacao>
          </locPrest>
          <cServ>
            <cTribNac>170501</cTribNac>
            <xDescServ>PRESTACAO DE SERVICOS DE APOIO OPERACIONAL E CONSERVACAO PREDIAL CONFORME MEDICAO 01/2026.</xDescServ>
            <cNBS>118012200</cNBS>
          </cServ>
          <infoCompl>
            <xInfComp>CONTRATO: CTR-2025/089. MEDICAO: 01/2026. DADOS BANCARIOS: BANCO ITAU, AG: 1234, C/C: 56789-0. CHAVE PIX: 12345678000199. DEDUCOES: VT: R$ 450,00 | VR: R$ 680,00 CONFORME ART 121 IN RFB 971.</xInfComp>
          </infoCompl>
        </serv>
        <valores>
          <vServPrest>
            <vServ>8774.20</vServ>
          </vServPrest>
          <trib>
            <tribMun>
              <tribISSQN>1</tribISSQN>
              <tpRetISSQN>2</tpRetISSQN>
            </tribMun>
            <tribFed>
              <piscofins>
                <CST>01</CST>
                <vBCPisCofins>8774.20</vBCPisCofins>
                <pAliqPis>0.65</pAliqPis>
                <pAliqCofins>3.00</pAliqCofins>
                <vPis>57.03</vPis>
                <vCofins>263.23</vCofins>
                <tpRetPisCofins>0</tpRetPisCofins>
              </piscofins>
              <vRetCP>722.34</vRetCP>
            </tribFed>
            <totTrib>
              <pTotTrib>
                <pTotTribFed>13.45</pTotTribFed>
                <pTotTribEst>0.00</pTotTribEst>
                <pTotTribMun>5.00</pTotTribMun>
              </pTotTrib>
            </totTrib>
          </trib>
        </valores>
      </infDPS>
    </DPS>
  </infNFSe>
  <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
    <SignedInfo>
      <Reference URI="#NFS31470062410100000000000000000000000000000000000001">
        <DigestValue>dGVzdGUtZGlnZXN0LWRvYy0xLW5mc2UtbmFjaW9uYWw=</DigestValue>
      </Reference>
    </SignedInfo>
    <SignatureValue>U2lnbmF0dXJlVmFsdWVEb2MxRXhlbXBsYXJDb21wbGV0bw==</SignatureValue>
  </Signature>
</NFSe>
"""

SAMPLE_DOC_16 = """<?xml version="1.0" encoding="UTF-8"?>
<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">
  <infNFSe Id="NFS35503082410200000000000000000000000000000000000016">
    <xLocEmi>Sao Paulo</xLocEmi>
    <xLocPrestacao>Sao Paulo</xLocPrestacao>
    <nNFSe>2016</nNFSe>
    <cLocIncid>3550308</cLocIncid>
    <xLocIncid>Sao Paulo</xLocIncid>
    <xTribNac>Desenvolvimento de programas de computador sob encomenda</xTribNac>
    <xNBS>Servicos de TI e programacao</xNBS>
    <verAplic>EmissorWeb_1.5.0.0</verAplic>
    <ambGer>1</ambGer>
    <tpEmis>1</tpEmis>
    <procEmi>2</procEmi>
    <cStat>100</cStat>
    <dhProc>2026-02-10T09:12:33-03:00</dhProc>
    <nDFSe>612340</nDFSe>
    <emit>
      <CNPJ>23456789000188</CNPJ>
      <xNome>CODEX TECH INOVACOES DIGITAIS LTDA</xNome>
      <enderNac>
        <xLgr>Avenida Paulista</xLgr>
        <nro>1500</nro>
        <xBairro>Bela Vista</xBairro>
        <cMun>3550308</cMun>
        <UF>SP</UF>
        <CEP>01310100</CEP>
      </enderNac>
      <fone>1130034000</fone>
      <email>contato@codextech.io</email>
    </emit>
    <valores>
      <vBC>12500.00</vBC>
      <pAliqAplic>2.79</pAliqAplic>
      <vISSQN>348.75</vISSQN>
      <vLiq>12500.00</vLiq>
    </valores>
    <DPS versao="1.01">
      <infDPS Id="DPS35503082410200000000000000000000000000000000000016">
        <tpAmb>1</tpAmb>
        <dhEmi>2026-02-10T08:50:00-03:00</dhEmi>
        <verAplic>EmissorWeb_1.4.0.26</verAplic>
        <serie>70000</serie>
        <nDPS>2016</nDPS>
        <dCompet>2026-02-10</dCompet>
        <tpEmit>1</tpEmit>
        <cLocEmi>3550308</cLocEmi>
        <prest>
          <CNPJ>23456789000188</CNPJ>
          <regTrib>
            <opSimpNac>2</opSimpNac>
            <regEspTrib>0</regEspTrib>
          </regTrib>
        </prest>
        <toma>
          <CNPJ>45678901000122</CNPJ>
          <xNome>FINTECH HORIZONTE SERVICOS FINANCEIROS LTDA</xNome>
          <end>
            <endNac>
              <cMun>3550308</cMun>
              <CEP>04543011</CEP>
            </endNac>
            <xLgr>Avenida Brigadeiro Faria Lima</xLgr>
            <nro>3477</nro>
            <xBairro>Itaim Bibi</xBairro>
          </end>
        </toma>
        <serv>
          <locPrest>
            <cLocPrestacao>3550308</cLocPrestacao>
          </locPrest>
          <cServ>
            <cTribNac>010101</cTribNac>
            <xDescServ>DESENVOLVIMENTO DE APIs E ARQUITETURA DE MICROSSERVICOS CONFORME SPRINT 14.</xDescServ>
            <cNBS>115011100</cNBS>
          </cServ>
          <infoCompl>
            <xInfComp>DOCUMENTO EMITIDO POR ME OU EPP OPTANTE PELO SIMPLES NACIONAL. NAO GERA DIREITO A CREDITO FISCAL DE IPI. BANCO NUBANK, CHAVE PIX: contato@codextech.io. PO: 440912.</xInfComp>
          </infoCompl>
        </serv>
        <valores>
          <vServPrest>
            <vServ>12500.00</vServ>
          </vServPrest>
          <trib>
            <tribMun>
              <tribISSQN>1</tribISSQN>
              <tpRetISSQN>1</tpRetISSQN>
            </tribMun>
            <tribFed>
              <piscofins>
                <CST>07</CST>
                <vBCPisCofins>0.00</vBCPisCofins>
                <pAliqPis>0.00</pAliqPis>
                <pAliqCofins>0.00</pAliqCofins>
                <vPis>0.00</vPis>
                <vCofins>0.00</vCofins>
                <tpRetPisCofins>0</tpRetPisCofins>
              </piscofins>
            </tribFed>
            <totTrib>
              <pTotTrib>
                <pTotTribFed>4.25</pTotTribFed>
                <pTotTribEst>0.00</pTotTribEst>
                <pTotTribMun>2.79</pTotTribMun>
              </pTotTrib>
            </totTrib>
          </trib>
        </valores>
      </infDPS>
    </DPS>
  </infNFSe>
  <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
    <SignedInfo>
      <Reference URI="#NFS35503082410200000000000000000000000000000000000016">
        <DigestValue>ZGlnZXN0LWRvYy0xNi1zb2Z0d2FyZQ==</DigestValue>
      </Reference>
    </SignedInfo>
    <SignatureValue>U2lnbmF0dXJlVmFsdWVEb2MxNlNpbXBsZXNOYWNpb25hbA==</SignatureValue>
  </Signature>
</NFSe>
"""

SAMPLE_DOC_18 = """<?xml version="1.0" encoding="UTF-8"?>
<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">
  <infNFSe Id="NFS31062002410300000000000000000000000000000000000018">
    <xLocEmi>Belo Horizonte</xLocEmi>
    <xLocPrestacao>Belo Horizonte</xLocPrestacao>
    <nNFSe>3018</nNFSe>
    <cLocIncid>3106200</cLocIncid>
    <xLocIncid>Belo Horizonte</xLocIncid>
    <xTribNac>Vigilancia, seguranca ou monitoramento de bens e pessoas</xTribNac>
    <xNBS>Servicos de seguranca armada e desarmada</xNBS>
    <verAplic>EmissorWeb_1.5.0.0</verAplic>
    <ambGer>1</ambGer>
    <tpEmis>1</tpEmis>
    <procEmi>2</procEmi>
    <cStat>100</cStat>
    <dhProc>2026-03-05T16:44:20-03:00</dhProc>
    <nDFSe>793102</nDFSe>
    <emit>
      <CNPJ>34567890000177</CNPJ>
      <xNome>FORTALEZA SEGURANCA E VIGILANCIA PATRIMONIAL LTDA</xNome>
      <enderNac>
        <xLgr>Rua da Bahia</xLgr>
        <nro>1200</nro>
        <xBairro>Lourdes</xBairro>
        <cMun>3106200</cMun>
        <UF>MG</UF>
        <CEP>30160011</CEP>
      </enderNac>
      <fone>3132221100</fone>
      <email>financeiro@fortalezaseg.com.br</email>
    </emit>
    <valores>
      <vBC>5426.60</vBC>
      <pAliqAplic>5.00</pAliqAplic>
      <vISSQN>271.33</vISSQN>
      <vTotalRet>746.16</vTotalRet>
      <vLiq>4680.44</vLiq>
    </valores>
    <DPS versao="1.01">
      <infDPS Id="DPS31062002410300000000000000000000000000000000000018">
        <tpAmb>1</tpAmb>
        <dhEmi>2026-03-05T16:00:00-03:00</dhEmi>
        <verAplic>EmissorWeb_1.4.0.26</verAplic>
        <serie>900</serie>
        <nDPS>3018</nDPS>
        <dCompet>2026-03-05</dCompet>
        <tpEmit>1</tpEmit>
        <cLocEmi>3106200</cLocEmi>
        <prest>
          <CNPJ>34567890000177</CNPJ>
          <regTrib>
            <opSimpNac>1</opSimpNac>
            <regEspTrib>0</regEspTrib>
          </regTrib>
        </prest>
        <toma>
          <CNPJ>56789012000166</CNPJ>
          <xNome>CONDOMINIO DO EDIFICIO METROPOLIS TOWER</xNome>
          <end>
            <endNac>
              <cMun>3106200</cMun>
              <CEP>30130000</CEP>
            </endNac>
            <xLgr>Avenida Afonso Pena</xLgr>
            <nro>4000</nro>
            <xCpl>Bloco B - Cobertura</xCpl>
            <xBairro>Cruzeiro</xBairro>
          </end>
        </toma>
        <serv>
          <locPrest>
            <cLocPrestacao>3106200</cLocPrestacao>
          </locPrest>
          <cServ>
            <cTribNac>110201</cTribNac>
            <xDescServ>SERVICOS DE VIGILANCIA DESARMADA E PORTARIA 24H CONFORME ESCALA MENSAL.</xDescServ>
            <cNBS>118021100</cNBS>
          </cServ>
          <infoCompl>
            <xInfComp>RETENCOES: ISS RETIDO R$ 271,33 + INSS RETIDO R$ 474,83 = TOTAL RETENCOES R$ 746,16. BANCO BRADESCO, AGENCIA: 0456, CONTA: 89012-3. CHAVE PIX: financeiro@fortalezaseg.com.br. CONTRATO: CT-441-2024.</xInfComp>
          </infoCompl>
        </serv>
        <valores>
          <vServPrest>
            <vServ>5426.60</vServ>
          </vServPrest>
          <trib>
            <tribMun>
              <tribISSQN>1</tribISSQN>
              <tpRetISSQN>2</tpRetISSQN>
            </tribMun>
            <tribFed>
              <piscofins>
                <CST>01</CST>
                <vBCPisCofins>5426.60</vBCPisCofins>
                <pAliqPis>0.65</pAliqPis>
                <pAliqCofins>3.00</pAliqCofins>
                <vPis>35.27</vPis>
                <vCofins>162.80</vCofins>
                <tpRetPisCofins>0</tpRetPisCofins>
              </piscofins>
              <vRetCP>474.83</vRetCP>
            </tribFed>
            <totTrib>
              <pTotTrib>
                <pTotTribFed>12.80</pTotTribFed>
                <pTotTribEst>0.00</pTotTribEst>
                <pTotTribMun>5.00</pTotTribMun>
              </pTotTrib>
            </totTrib>
          </trib>
        </valores>
      </infDPS>
    </DPS>
  </infNFSe>
  <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
    <SignedInfo>
      <Reference URI="#NFS31062002410300000000000000000000000000000000000018">
        <DigestValue>ZGlnZXN0LWRvYy0xOC12aWdpbGFuY2lh</DigestValue>
      </Reference>
    </SignedInfo>
    <SignatureValue>U2lnbmF0dXJlVmFsdWVEb2MxOFZpZ2lsYW5jaWFBc3NpbmFkbw==</SignatureValue>
  </Signature>
</NFSe>
"""

SAMPLE_DOC_20 = """<?xml version="1.0" encoding="UTF-8"?>
<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">
  <infNFSe Id="NFS33045572410400000000000000000000000000000000000020">
    <xLocEmi>Rio de Janeiro</xLocEmi>
    <xLocPrestacao>Rio de Janeiro</xLocPrestacao>
    <nNFSe>4020</nNFSe>
    <cLocIncid>3304557</cLocIncid>
    <xLocIncid>Rio de Janeiro</xLocIncid>
    <xTribNac>Consultoria em publicidade e propaganda</xTribNac>
    <!-- xNBS ausente no doc 20 -->
    <verAplic>EmissorWeb_1.5.0.0</verAplic>
    <ambGer>1</ambGer>
    <tpEmis>1</tpEmis>
    <procEmi>2</procEmi>
    <cStat>100</cStat>
    <dhProc>2026-03-20T11:05:40-03:00</dhProc>
    <nDFSe>845190</nDFSe>
    <emit>
      <CNPJ>45678901000133</CNPJ>
      <xNome>RIO CRIATIVO COMUNICACAO INTEGRADA LTDA</xNome>
      <enderNac>
        <xLgr>Rua Visconde de Piraja</xLgr>
        <nro>300</nro>
        <xBairro>Ipanema</xBairro>
        <cMun>3304557</cMun>
        <UF>RJ</UF>
        <CEP>22410002</CEP>
      </enderNac>
      <fone>2125210000</fone>
      <email>fiscal@riocriativo.com.br</email>
    </emit>
    <valores>
      <vBC>18000.00</vBC>
      <pAliqAplic>5.00</pAliqAplic>
      <vISSQN>900.00</vISSQN>
      <vTotalRet>0.00</vTotalRet>
      <vLiq>18000.00</vLiq>
    </valores>
    <DPS versao="1.01">
      <infDPS Id="DPS33045572410400000000000000000000000000000000000020">
        <tpAmb>1</tpAmb>
        <dhEmi>2026-03-20T10:30:00-03:00</dhEmi>
        <verAplic>EmissorWeb_1.4.0.26</verAplic>
        <serie>900</serie>
        <nDPS>4020</nDPS>
        <dCompet>2026-03-20</dCompet>
        <tpEmit>1</tpEmit>
        <cLocEmi>3304557</cLocEmi>
        <prest>
          <CNPJ>45678901000133</CNPJ>
          <regTrib>
            <opSimpNac>1</opSimpNac>
            <regEspTrib>0</regEspTrib>
          </regTrib>
        </prest>
        <toma>
          <CNPJ>67890123000144</CNPJ>
          <xNome>VAREJO BRASIL LOGISTICA E DISTRIBUICAO S.A.</xNome>
          <end>
            <endNac>
              <cMun>3304557</cMun>
              <CEP>20040001</CEP>
            </endNac>
            <xLgr>Avenida Rio Branco</xLgr>
            <nro>156</nro>
            <xBairro>Centro</xBairro>
          </end>
        </toma>
        <serv>
          <locPrest>
            <cLocPrestacao>3304557</cLocPrestacao>
          </locPrest>
          <cServ>
            <cTribNac>100801</cTribNac>
            <xDescServ>PLANEJAMENTO ESTRATEGICO DE MARKETING E GESTAO DE MIDIA DIGITAL PARA O Q1 2026.</xDescServ>
            <!-- cNBS ausente no doc 20 -->
          </cServ>
          <infoCompl>
            <xInfComp>PAGAMENTO VIA PIX PARA O CNPJ: 45678901000133. BANCO SANTANDER, AGENCIA: 3344, CONTA: 13009876-5. PEDIDO: PED-8891.</xInfComp>
          </infoCompl>
        </serv>
        <valores>
          <vServPrest>
            <vServ>18000.00</vServ>
          </vServPrest>
          <trib>
            <tribMun>
              <tribISSQN>1</tribISSQN>
              <tpRetISSQN>1</tpRetISSQN>
            </tribMun>
            <tribFed>
              <piscofins>
                <CST>01</CST>
                <vBCPisCofins>18000.00</vBCPisCofins>
                <pAliqPis>1.65</pAliqPis>
                <pAliqCofins>7.60</pAliqCofins>
                <vPis>297.00</vPis>
                <vCofins>1368.00</vCofins>
                <tpRetPisCofins>0</tpRetPisCofins>
              </piscofins>
            </tribFed>
            <totTrib>
              <pTotTrib>
                <pTotTribFed>14.25</pTotTribFed>
                <pTotTribEst>0.00</pTotTribEst>
                <pTotTribMun>5.00</pTotTribMun>
              </pTotTrib>
            </totTrib>
          </trib>
        </valores>
      </infDPS>
    </DPS>
  </infNFSe>
  <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
    <SignedInfo>
      <Reference URI="#NFS33045572410400000000000000000000000000000000000020">
        <DigestValue>ZGlnZXN0LWRvYy0yMC1wdWJsaWNpZGFkZQ==</DigestValue>
      </Reference>
    </SignedInfo>
    <SignatureValue>U2lnbmF0dXJlVmFsdWVEb2MyMFB1YmxpY2lkYWRlQ29tcGxldGE=</SignatureValue>
  </Signature>
</NFSe>
"""

SAMPLE_FILES: Dict[str, str] = {
    "NFSe_Paracatu_Doc1_Retencao_ISS_INSS.xml": SAMPLE_DOC_1,
    "NFSe_SP_Doc16_Simples_Nacional_Sem_Retencao.xml": SAMPLE_DOC_16,
    "NFSe_BH_Doc18_Retencao_Condominio_xCpl.xml": SAMPLE_DOC_18,
    "NFSe_RJ_Doc20_Sem_NBS_Publicidade.xml": SAMPLE_DOC_20,
}


def create_sample_xml_files(target_dir: Path) -> List[Path]:
    """Cria os arquivos de exemplo no diretório especificado."""
    target_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for filename, content in SAMPLE_FILES.items():
        file_path = target_dir / filename
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content.strip())
        created.append(file_path)
    return created
