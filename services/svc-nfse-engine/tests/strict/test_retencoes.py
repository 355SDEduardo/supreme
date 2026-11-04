"""Regressões do relatório de retenções, sem alterar a base de dados local."""

import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient

from svc_nfse_engine.models import NFSNacionalModel, Participante, TributacaoFederal
from svc_nfse_engine.parser import NFSeNacionalParser
from svc_nfse_engine.retencoes import build_retention_report
from svc_nfse_engine.sample_generator import SAMPLE_FILES

# Importar as rotas sem inicializar a persistência real.
with patch("svc_nfse_engine.storage.JSONStorage"):
    from svc_nfse_engine.main import app


def make_note(key="teste", competencia=date(2026, 1, 15), **fields):
    return NFSNacionalModel(
        chave_nfse=key,
        numero_nfse=1,
        data_competencia=competencia,
        data_hora_processamento=datetime(2026, 10, 21),
        data_emissao_dps=datetime(2026, 2, 1),
        emitente=Participante(razao_social="Prestador de teste"),
        tomador=Participante(razao_social="Tomador de teste"),
        **{"tributos_federais": TributacaoFederal(), **fields},
    )


class RetentionReportTests(unittest.TestCase):
    def test_filters_by_competencia_not_emission_or_processing(self):
        notes = [
            make_note("janeiro", valor_total_retencoes=Decimal("10.25")),
            make_note("fevereiro", date(2026, 2, 1), valor_total_retencoes=Decimal("20")),
            make_note("outro-ano", date(2025, 1, 31), valor_total_retencoes=Decimal("30")),
            make_note("sem-retencao"),
        ]
        report = build_retention_report(notes, "2026-01")
        self.assertEqual(report["competencias"], ["2026-02", "2026-01", "2025-01"])
        self.assertEqual(report["total_notas_periodo"], 2)
        self.assertEqual(report["total_notas_retencao"], 1)
        self.assertEqual(report["notas"][0]["chave_nfse"], "janeiro")
        self.assertEqual(report["totais"]["total_declarado"], "10.25")
        self.assertEqual(build_retention_report(notes)["totais"]["total_declarado"], "60.25")

    def test_only_counts_withheld_taxes_and_includes_irrf_csll(self):
        for flag in (0, 1, 2):
            with self.subTest(flag=flag):
                note = make_note(
                    tipo_retencao_issqn=1,
                    valor_issqn=Decimal("50"),
                    tributos_federais=TributacaoFederal(
                        tp_retencao_pis_cofins=flag,
                        valor_pis=Decimal("1.65"),
                        valor_cofins=Decimal("7.60"),
                        valor_ret_cp_inss=Decimal("11"),
                        valor_ret_irrf=Decimal("1.50"),
                        valor_ret_csll=Decimal("1"),
                    ),
                )
                totals = build_retention_report([note])["totais"]
                self.assertEqual(totals["iss"], "0.00")
                self.assertEqual(totals["pis"], "0.00" if flag == 0 else "1.65")
                self.assertEqual(totals["cofins"], "0.00" if flag == 0 else "7.60")
                self.assertEqual(totals["inss"], "11.00")
                self.assertEqual(totals["irrf"], "1.50")
                self.assertEqual(totals["csll"], "1.00")

    def test_preserves_decimal_totals_and_declared_difference(self):
        notes = [make_note(str(i), tipo_retencao_issqn=2,
                           valor_issqn=Decimal("0.10"),
                           valor_total_retencoes=Decimal("0.20")) for i in range(3)]
        totals = build_retention_report(notes)["totais"]
        self.assertEqual(totals["iss"], "0.30")
        self.assertEqual(totals["total_identificado"], "0.30")
        self.assertEqual(totals["total_declarado"], "0.60")
        self.assertEqual(totals["diferenca"], "0.30")

    def test_empty_database_and_month_without_retention(self):
        for notes, month in (([], None), ([make_note()], "2026-01"),
                             ([make_note()], "2026-12")):
            with self.subTest(month=month, count=len(notes)):
                report = build_retention_report(notes, month)
                self.assertEqual(report["notas"], [])
                self.assertEqual(report["total_notas_retencao"], 0)
                self.assertTrue(all(value == "0.00" for value in report["totais"].values()))

    def test_all_four_xml_samples_remain_supported(self):
        notes = [NFSeNacionalParser.parse(xml.strip().encode("utf-8"), filename=name)
                 for name, xml in SAMPLE_FILES.items()]
        report = build_retention_report(notes)
        self.assertEqual(report["total_notas_periodo"], 4)
        self.assertEqual(report["total_notas_retencao"], 2)
        self.assertEqual(report["totais"]["total_declarado"], "1907.21")
        self.assertEqual(
            Decimal(report["totais"]["total_identificado"]),
            sum(note.auditoria.total_retencoes_calculado for note in notes),
        )
        no_retention = next(note for note in notes if "Doc16" in note.arquivo_origem)
        self.assertNotIn(no_retention.chave_nfse, [row["chave_nfse"] for row in report["notas"]])


class RetentionApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.storage_patch = patch("svc_nfse_engine.main.storage")
        self.storage = self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)
        self.storage.get_all_notes.return_value = [
            make_note(valor_total_retencoes=Decimal("5")),
            make_note("fevereiro", date(2026, 2, 1), valor_total_retencoes=Decimal("10")),
        ]

    def test_endpoint_with_and_without_filter(self):
        response = self.client.get("/api/retencoes", params={"competencia": "2026-01"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["totais"]["total_declarado"], "5.00")
        self.assertEqual(self.client.get("/api/retencoes").json()["total_notas_retencao"], 2)

    def test_valid_month_without_results(self):
        response = self.client.get("/api/retencoes?competencia=2026-12")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["notas"], [])

    def test_invalid_competencias_are_rejected(self):
        for month in ("2026-00", "2026-13", "2026-1", "01/2026", "2026-01-01", "0000-01", ""):
            with self.subTest(month=month):
                response = self.client.get("/api/retencoes", params={"competencia": month})
                self.assertEqual(response.status_code, 422)
        self.storage.get_all_notes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
