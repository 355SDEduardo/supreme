"""Adapt the documentary engine's prototype assumptions to tenant datasets."""
from datetime import datetime
from pathlib import Path
import json
from .tools.audit_engine import FederalTaxAuditEngine as OriginalEngine

class FederalTaxAuditEngine(OriginalEngine):
    def load_all(self):
        super().load_all()
        configuration = Path(self.workspace_path) / 'audit_config.json'
        settings = json.loads(configuration.read_text(encoding='utf-8')) if configuration.exists() else {}
        cutoff = settings.get('ledger_end')
        ledger = set(self.servicos_data.get('notas_escrituradas', []))
        for note in self.nfse_data:
            code = note.get('status', 100)
            note['status_codigo'] = code
            note['status_descricao'] = '100 - Autorizada' if code == 100 else f'{code} - Conferir evento fiscal'
            if note['numero_nfse'] in ledger:
                status, description = 'ESCRITURADA_A_CONFERIR', 'Número localizado no livro; conferir valores e identidade.'
            elif not self.servicos_data:
                status, description = 'NAO_LOCALIZADA_SEM_LIVRO', 'Livro fiscal não fornecido para esta empresa.'
            elif cutoff and note.get('data_emissao_iso','')[:10] > cutoff:
                status, description = 'NAO_LOCALIZADA_PERIODO_POSTERIOR', 'Emissão posterior ao encerramento informado do livro.'
            else:
                status, description = 'NAO_LOCALIZADA_PERIODO_A_CONFERIR', 'Nota ausente no livro fornecido; conferir cobertura temporal.'
            note['situacao_livro'], note['situacao_livro_descricao'] = status, description

    def run_full_audit(self):
        result = super().run_full_audit()
        cutoff_file = Path(self.workspace_path) / 'audit_config.json'
        settings = json.loads(cutoff_file.read_text(encoding='utf-8')) if cutoff_file.exists() else {}
        cutoff = settings.get('ledger_end')
        missing = result.get('notas_ausentes_no_livro', {})
        for row in missing.get('detalhes', []):
            row['classificacao_corte'] = ('POSTERIOR_AO_LIVRO' if cutoff and row.get('data_emissao','')[:10] > cutoff
                                          else 'PERIODO_COBERTO' if cutoff else 'COBERTURA_NAO_INFORMADA')
        segregation = missing.get('segregacao_corte_temporal', {})
        for name, value in segregation.items():
            if isinstance(value,dict):
                value['descricao'] = 'Segregação conforme cobertura temporal informada para o livro fiscal.'
        result['confronto_inverso_livro'] = {key:value for key,value in result.get('confronto_inverso_livro',{}).items() if key not in {'descricao','observacao'}}
        return result
