"""Synthetic service documents only; no real taxpayer data."""
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

KEY = '3' * 50
NATIONAL_URI = 'http://www.sped.fazenda.gov.br/nfse'


def national(*, key=KEY, retention='1', simple='1', rate='5.00', net='9750.00',
             gross='10000.00', rtc=False, subcode='010701', incidence='3550308', execution='3550308'):
    reform = '''<IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib><vBC>10000.00</vBC>
        <pIBSUF>0.10</pIBSUF><vIBSUF>10.00</vIBSUF><pIBSMun>0.10</pIBSMun><vIBSMun>10.00</vIBSMun>
        <pCBS>0.90</pCBS><vCBS>90.00</vCBS><vTotIBS>20.00</vTotIBS><vTotCBS>90.00</vTotCBS><vTotNF>10110.00</vTotNF></IBSCBS>''' if rtc else ''
    withheld = '750.00' if retention in {'2', '3'} else '250.00'
    return f'''<NFSe xmlns="{NATIONAL_URI}" versao="1.01"><infNFSe Id="NFS{key}">
        <nNFSe>000123</nNFSe><serie>01</serie><dhProc>2026-03-10T14:32:00-03:00</dhProc>
        <emit><CNPJ>00000000000100</CNPJ><xNome>Órgão emissor</xNome><cMun>3550308</cMun></emit>
        <cLocIncid>{incidence}</cLocIncid><DPS versao="1.01"><infDPS Id="DPS001">
        <nDPS>000012</nDPS><serie>001</serie><dhEmi>2026-03-10T10:00:00-03:00</dhEmi><dCompet>2026-03-01</dCompet>
        <prest><CNPJ>12.ABC.345/01DE-35</CNPJ><xNome>Prestadora sintética</xNome><IM>0012</IM><cMun>3550308</cMun>
        <regTrib><opSimpNac>{simple}</opSimpNac></regTrib></prest>
        <toma><CNPJ>00111222000133</CNPJ><xNome>Tomadora sintética</xNome><cMun>3106200</cMun></toma>
        <serv><locPrest><cLocPrestacao>{execution}</cLocPrestacao></locPrest><cServ><cTribNac>{subcode}</cTribNac><cTribMun>001</cTribMun>
        <xDescServ>Consultoria em sistemas</xDescServ></cServ></serv>
        <valores><vServPrest><vServ>{gross}</vServ></vServPrest><vDescIncond>0.00</vDescIncond><vDescCond>0.00</vDescCond>
        <trib><tribMun><tpRetISSQN>{retention}</tpRetISSQN><pAliq>5.00</pAliq></tribMun>
        <tribFed><vRetIRRF>150.00</vRetIRRF><vRetCP>0.00</vRetCP><vRetCSLL>100.00</vRetCSLL></tribFed></trib></valores>
        </infDPS></DPS><valores><vBC>10000.00</vBC><pAliqAplic>{rate}</pAliqAplic><vISSQN>500.00</vISSQN>
        <vTotalRet>{withheld}</vTotalRet><vLiq>{net}</vLiq></valores>{reform}</infNFSe></NFSe>'''.encode()


def abrasf(*, version='2.04', rate='0.05', number='001', cancelled=False, multiple=False, namespace='http://www.abrasf.org.br/nfse.xsd'):
    service = f'''<Servico><Valores><ValorServicos>5000.00</ValorServicos><ValorIss>250.00</ValorIss><Aliquota>{rate}</Aliquota>
        <ValorIr>75.00</ValorIr><ValorPis>32.50</ValorPis><ValorCofins>150.00</ValorCofins><ValorCsll>50.00</ValorCsll></Valores>
        <IssRetido>2</IssRetido><ItemListaServico>107</ItemListaServico><Discriminacao>Serviço teste</Discriminacao>
        <MunicipioPrestacaoServico>3106200</MunicipioPrestacaoServico><MunicipioIncidencia>3106200</MunicipioIncidencia></Servico>'''
    declaration = service + (service if multiple else '') + '''<Prestador><CpfCnpj><Cnpj>00111222000133</Cnpj></CpfCnpj><RazaoSocial>Prestador ABRASF</RazaoSocial>
        <CodigoMunicipio>3106200</CodigoMunicipio></Prestador><Tomador><CpfCnpj><Cnpj>00999888000155</Cnpj></CpfCnpj>
        <RazaoSocial>Tomador</RazaoSocial></Tomador><Competencia>2026-02-01</Competencia><OptanteSimplesNacional>2</OptanteSimplesNacional>'''
    if version.startswith('2.'):
        declaration = '<DeclaracaoPrestacaoServico><InfDeclaracaoPrestacaoServico>' + declaration + '</InfDeclaracaoPrestacaoServico></DeclaracaoPrestacaoServico>'
    cancel = '<NfseCancelamento><Confirmacao><DataHora>2026-02-20T16:00:00</DataHora><Pedido><InfPedidoCancelamento><CodigoCancelamento>1</CodigoCancelamento></InfPedidoCancelamento></Pedido></Confirmacao></NfseCancelamento>' if cancelled else ''
    return f'''<CompNfse xmlns="{namespace}"><Nfse versao="{version}"><InfNfse Id="N{number}"><Numero>{number}</Numero><DataEmissao>2026-02-15T10:30:00</DataEmissao>
        {declaration}<OrgaoGerador><CodigoMunicipio>3106200</CodigoMunicipio></OrgaoGerador>
        <ValoresNfse><BaseCalculo>{'10000.00' if multiple else '5000.00'}</BaseCalculo><Aliquota>5.00</Aliquota>
        <ValorIss>{'500.00' if multiple else '250.00'}</ValorIss><ValorLiquidoNfse>{'9385.00' if multiple else '4692.50'}</ValorLiquidoNfse></ValoresNfse>
        </InfNfse></Nfse>{cancel}</CompNfse>'''.encode()


def paulistana():
    return b'''<NFe xmlns="http://www.prefeitura.sp.gov.br/nfe"><ChaveNFe><InscricaoPrestador>00123</InscricaoPrestador>
        <NumeroNFe>00045</NumeroNFe><CodigoVerificacao>ABC123</CodigoVerificacao></ChaveNFe><DataEmissao>2026-03-01T14:20:00</DataEmissao>
        <CPFCNPJPrestador><CNPJ>00111222000133</CNPJ></CPFCNPJPrestador><RazaoSocialPrestador>Paulistana</RazaoSocialPrestador>
        <OpcaoSimples>0</OpcaoSimples><ValorServicos>15000.00</ValorServicos><CodigoServico>02682</CodigoServico>
        <AliquotaServicos>0.05</AliquotaServicos><ValorISS>750.00</ValorISS><ISSRetido>false</ISSRetido>
        <ValorIR>225.00</ValorIR><ValorCSLL>150.00</ValorCSLL><ValorPIS>97.50</ValorPIS><ValorCOFINS>450.00</ValorCOFINS>
        <ValorLiquido>14077.50</ValorLiquido></NFe>'''


def event(*, key=KEY, code='e101101', substitute='', stamp='2026-03-12T15:00:00-03:00'):
    return f'''<PEDREGEVT_EVT xmlns="{NATIONAL_URI}"><infPedReg><chNFSe>{key}</chNFSe><tpEvento>{code}</tpEvento>
        <nPedRegEvento>1</nPedRegEvento><dhPedReg>{stamp}</dhPedReg><detEvento><xJust>Teste de evento</xJust>
        <chSubst>{substitute}</chSubst></detEvento></infPedReg></PEDREGEVT_EVT>'''.encode()


def zipped(entries):
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()
