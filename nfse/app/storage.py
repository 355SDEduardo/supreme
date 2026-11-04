"""
Módulo de Armazenamento e Persistência de NFS-e em formato JSON.
Gera arquivos .json individuais formatados para cada nota e mantém
uma base consolidada indexada para consultas instantâneas no dashboard.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
from decimal import Decimal

from app.models import NFSNacionalModel


class JSONStorage:
    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            # Diretório raiz do projeto
            self.base_dir = Path(__file__).resolve().parent.parent / "data"
        else:
            self.base_dir = base_dir

        self.json_dir = self.base_dir / "json"
        self.xml_dir = self.base_dir / "xml"
        self.db_file = self.base_dir / "database.json"

        # Garantir diretórios
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.xml_dir.mkdir(parents=True, exist_ok=True)

        # Inicializar arquivo de índice se não existir
        if not self.db_file.exists():
            self._write_db({"notes": {}, "updated_at": datetime.now().isoformat()})

    def _read_db(self) -> Dict[str, Any]:
        try:
            if self.db_file.exists():
                with open(self.db_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"notes": {}, "updated_at": datetime.now().isoformat()}

    def _write_db(self, data: Dict[str, Any]) -> None:
        data["updated_at"] = datetime.now().isoformat()
        with open(self.db_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save_note(
        self,
        note: NFSNacionalModel,
        xml_bytes: Optional[bytes] = None,
    ) -> Path:
        """
        Salva a nota fiscal em um arquivo .json estruturado exclusivo e indexa na base.
        """
        # Nome único de arquivo sanitizado
        clean_key = "".join(c for c in note.chave_nfse if c.isalnum() or c in ("-", "_"))
        if not clean_key:
            clean_key = f"NFSe_{note.numero_nfse}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        filename = f"{clean_key}.json"
        file_path = self.json_dir / filename

        # Serializa para dicionário Pydantic com tipos primitivos prontos para JSON
        note_dict = note.model_dump(mode="json")

        # Salva o arquivo .json individual
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(note_dict, f, ensure_ascii=False, indent=2)

        # Salva o XML original associado se fornecido
        if xml_bytes:
            xml_path = self.xml_dir / f"{clean_key}.xml"
            with open(xml_path, "wb") as f:
                f.write(xml_bytes)

        # Atualiza a base consolidada
        db = self._read_db()
        db["notes"][note.chave_nfse] = note_dict
        self._write_db(db)

        return file_path

    def get_note_by_key(self, chave: str) -> Optional[NFSNacionalModel]:
        """Obtém nota pela chave de acesso."""
        db = self._read_db()
        raw = db["notes"].get(chave)
        if raw:
            return NFSNacionalModel.model_validate(raw)

        # Tentar ler direto do arquivo json
        clean_key = "".join(c for c in chave if c.isalnum() or c in ("-", "_"))
        target_file = self.json_dir / f"{clean_key}.json"
        if target_file.exists():
            with open(target_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                return NFSNacionalModel.model_validate(raw_data)

        return None

    def get_all_notes(self) -> List[NFSNacionalModel]:
        """Retorna todas as notas fiscais cadastradas."""
        db = self._read_db()
        notes = []
        for raw in db["notes"].values():
            try:
                notes.append(NFSNacionalModel.model_validate(raw))
            except Exception:
                continue

        # Ordenar por data de processamento / competência decrescente
        notes.sort(key=lambda x: x.data_hora_processamento, reverse=True)
        return notes

    def delete_note(self, chave: str) -> bool:
        """Remove nota do JSON e da base."""
        db = self._read_db()
        if chave in db["notes"]:
            del db["notes"][chave]
            self._write_db(db)

        clean_key = "".join(c for c in chave if c.isalnum() or c in ("-", "_"))
        json_path = self.json_dir / f"{clean_key}.json"
        if json_path.exists():
            json_path.unlink()

        xml_path = self.xml_dir / f"{clean_key}.xml"
        if xml_path.exists():
            xml_path.unlink()

        return True

    def clear_all(self) -> None:
        """Limpa toda a base de dados e arquivos JSON/XML salvos."""
        for p in self.json_dir.glob("*.json"):
            p.unlink()
        for p in self.xml_dir.glob("*.xml"):
            p.unlink()
        self._write_db({"notes": {}, "updated_at": datetime.now().isoformat()})

    def get_kpis_and_analytics(self) -> Dict[str, Any]:
        """Calcula métricas contábeis consolidadas para o dashboard."""
        notes = self.get_all_notes()
        total_notas = len(notes)

        if total_notas == 0:
            return {
                "total_notas": 0,
                "faturamento_bruto": 0.0,
                "faturamento_liquido": 0.0,
                "total_retencoes": 0.0,
                "iss_proprio": 0.0,
                "iss_retido": 0.0,
                "inss_retido": 0.0,
                "pis_cofins_total": 0.0,
                "taxa_conformidade": 100.0,
                "notas_conciliadas": 0,
                "notas_inconsistentes": 0,
                "timeline": [],
                "top_tomadores": [],
                "composicao_retencoes": {
                    "ISS Retido": 0.0,
                    "INSS": 0.0,
                    "PIS/COFINS": 0.0,
                    "Outros/IRRF/CSLL": 0.0,
                },
                "por_municipio": [],
                "por_tributacao": [],
            }

        faturamento_bruto = sum(n.valor_servico for n in notes)
        faturamento_liquido = sum(n.valor_liquido for n in notes)
        total_retencoes = sum(n.valor_total_retencoes for n in notes)

        iss_retido = sum(
            n.valor_issqn for n in notes if n.tipo_retencao_issqn == 2
        )
        iss_proprio = sum(
            n.valor_issqn for n in notes if n.tipo_retencao_issqn != 2
        )
        inss_retido = sum(n.tributos_federais.valor_ret_cp_inss for n in notes)
        pis_cofins_total = sum(
            (n.tributos_federais.valor_pis + n.tributos_federais.valor_cofins)
            for n in notes
        )
        outros_federais = sum(
            (n.tributos_federais.valor_ret_irrf + n.tributos_federais.valor_ret_csll)
            for n in notes
        )

        conciliadas = sum(
            1 for n in notes if n.auditoria.status_conciliacao == "CONCILIADO"
        )
        taxa_conformidade = (conciliadas / total_notas * 100) if total_notas > 0 else 100.0

        # Timeline por competência / data
        timeline_dict: Dict[str, Dict[str, float]] = {}
        for n in reversed(notes):
            key = n.data_competencia.strftime("%Y-%m")
            if key not in timeline_dict:
                timeline_dict[key] = {
                    "competencia": key,
                    "bruto": 0.0,
                    "liquido": 0.0,
                    "retencoes": 0.0,
                    "qtd": 0,
                }
            timeline_dict[key]["bruto"] += float(n.valor_servico)
            timeline_dict[key]["liquido"] += float(n.valor_liquido)
            timeline_dict[key]["retencoes"] += float(n.valor_total_retencoes)
            timeline_dict[key]["qtd"] += 1

        timeline = sorted(timeline_dict.values(), key=lambda x: x["competencia"])

        # Top tomadores
        tomadores_dict: Dict[str, Dict[str, Any]] = {}
        for n in notes:
            nome = n.tomador.razao_social or n.tomador.cnpj or "Não informado"
            if nome not in tomadores_dict:
                tomadores_dict[nome] = {
                    "nome": nome,
                    "documento": n.tomador.documento_formatado,
                    "total_faturado": 0.0,
                    "total_retido": 0.0,
                    "qtd_notas": 0,
                }
            tomadores_dict[nome]["total_faturado"] += float(n.valor_servico)
            tomadores_dict[nome]["total_retido"] += float(n.valor_total_retencoes)
            tomadores_dict[nome]["qtd_notas"] += 1

        top_tomadores = sorted(
            tomadores_dict.values(),
            key=lambda x: x["total_faturado"],
            reverse=True,
        )[:10]

        # Distribuição por Município
        mun_dict: Dict[str, float] = {}
        for n in notes:
            loc = n.local_prestacao or n.local_incidencia or n.local_emissao or "Desconhecido"
            mun_dict[loc] = mun_dict.get(loc, 0.0) + float(n.valor_servico)

        por_municipio = [
            {"municipio": k, "valor": v}
            for k, v in sorted(mun_dict.items(), key=lambda x: x[1], reverse=True)[:8]
        ]

        # Distribuição por Código Tributação Nacional
        trib_dict: Dict[str, Dict[str, Any]] = {}
        for n in notes:
            code = n.codigo_tributacao_nacional or "Outros"
            desc = n.tributacao_nacional_desc or "Serviço Municipal"
            if code not in trib_dict:
                trib_dict[code] = {"codigo": code, "descricao": desc, "total": 0.0, "qtd": 0}
            trib_dict[code]["total"] += float(n.valor_servico)
            trib_dict[code]["qtd"] += 1

        por_tributacao = sorted(trib_dict.values(), key=lambda x: x["total"], reverse=True)[:8]

        return {
            "total_notas": total_notas,
            "faturamento_bruto": float(faturamento_bruto),
            "faturamento_liquido": float(faturamento_liquido),
            "total_retencoes": float(total_retencoes),
            "iss_proprio": float(iss_proprio),
            "iss_retido": float(iss_retido),
            "inss_retido": float(inss_retido),
            "pis_cofins_total": float(pis_cofins_total),
            "taxa_conformidade": round(taxa_conformidade, 1),
            "notas_conciliadas": conciliadas,
            "notas_inconsistentes": total_notas - conciliadas,
            "timeline": timeline,
            "top_tomadores": top_tomadores,
            "composicao_retencoes": {
                "ISS Retido": round(float(iss_retido), 2),
                "INSS Retido": round(float(inss_retido), 2),
                "PIS/COFINS": round(float(pis_cofins_total), 2),
                "Outras / Federais": round(float(outros_federais), 2),
            },
            "por_municipio": por_municipio,
            "por_tributacao": por_tributacao,
        }
