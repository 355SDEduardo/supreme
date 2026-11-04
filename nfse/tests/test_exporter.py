"""Validação dos arquivos XLSX gerados e do download pela API."""

import io
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import get_type_hints
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.exporter import NFSeExporter
from app.parser import NFSeNacionalParser
from app.sample_generator import SAMPLE_FILES
from app.storage import JSONStorage

with patch("app.storage.JSONStorage"):
    from app.main import app


SHEETS = ["Resumo Gerencial", "Notas Fiscais", "Retenções na Fonte e INSS", "PIX e Complementares"]


class ExcelExporterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notes = [
            NFSeNacionalParser.parse(xml.strip().encode("utf-8"), filename=name)
            for name, xml in SAMPLE_FILES.items()
        ]

    def read_workbook(self, content):
        with ZipFile(io.BytesIO(content)) as archive:
            self.assertIsNone(archive.testzip())
        workbook = load_workbook(io.BytesIO(content), data_only=True)
        self.addCleanup(workbook.close)
        self.assertEqual(workbook.sheetnames, SHEETS)
        return workbook

    def test_summary_totals_and_percentages_match_invoice_values(self):
        workbook = self.read_workbook(NFSeExporter.generate_excel(self.notes))
        sheet = workbook["Resumo Gerencial"]
        self.assertEqual(sheet["A4"].value, "Indicador Fiscal / Contábil")
        expected = [
            sum(n.valor_servico for n in self.notes),
            sum(n.valor_liquido for n in self.notes),
            sum(n.valor_total_retencoes for n in self.notes),
            sum(n.valor_issqn for n in self.notes if not n.iss_retido_pelo_tomador),
            sum(n.valor_issqn for n in self.notes if n.iss_retido_pelo_tomador),
            sum(n.tributos_federais.valor_ret_cp_inss for n in self.notes),
            sum(n.tributos_federais.valor_pis for n in self.notes),
            sum(n.tributos_federais.valor_cofins for n in self.notes),
        ]
        for row, amount in enumerate(expected, start=5):
            with self.subTest(row=row):
                self.assertEqual(Decimal(str(sheet.cell(row, 2).value)), amount)
                self.assertAlmostEqual(sheet.cell(row, 3).value, float(amount / expected[0]))
                self.assertEqual(sheet.cell(row, 2).number_format, NFSeExporter.FORMAT_CURRENCY)
                self.assertEqual(sheet.cell(row, 3).number_format, NFSeExporter.FORMAT_PERCENT)

    def test_period_label_does_not_overwrite_financial_header(self):
        workbook = self.read_workbook(NFSeExporter.generate_excel(self.notes, periodo_info="01/2026 a 03/2026"))
        sheet = workbook["Resumo Gerencial"]
        self.assertEqual(sheet["A3"].value, "Período Selecionado: 01/2026 a 03/2026")
        self.assertEqual(sheet["A5"].value, "Indicador Fiscal / Contábil")
        self.assertEqual(sheet["B5"].value, "Valor Total (R$)")
        self.assertEqual(sheet["A6"].value, "Faturamento Bruto Total (vServ)")
        self.assertEqual(Decimal(str(sheet["B6"].value)), sum(n.valor_servico for n in self.notes))

    def test_all_detail_sheets_preserve_four_samples_and_optional_fields(self):
        workbook = self.read_workbook(NFSeExporter.generate_excel(self.notes))
        for name in SHEETS[1:]:
            sheet = workbook[name]
            self.assertEqual(sheet.max_row, 5)
            self.assertEqual([sheet.cell(row, 1).value for row in range(2, 6)],
                             [n.numero_nfse for n in self.notes])
        for row, note in enumerate(self.notes, start=2):
            detail = workbook["Notas Fiscais"]
            detail_columns = {cell.value: cell.column for cell in detail[1]}
            self.assertEqual(detail.cell(row, 2).value, note.chave_nfse)
            self.assertEqual(detail.cell(row, 17).value, note.codigo_nbs or "-")
            self.assertEqual(Decimal(str(detail.cell(row, 18).value)), note.valor_servico)
            self.assertEqual(Decimal(str(detail.cell(row, detail_columns["Total Retenções (R$)"]).value)),
                             note.valor_total_retencoes)
            retention = workbook["Retenções na Fonte e INSS"]
            retention_columns = {cell.value: cell.column for cell in retention[1]}
            self.assertEqual(Decimal(str(retention.cell(row, retention_columns["Total Retenções (R$)"]).value)),
                             note.valor_total_retencoes)
            extra = workbook["PIX e Complementares"]
            self.assertEqual(extra.cell(row, 3).value, note.dados_complementares_extraidos.chave_pix or "-")

    def test_zero_revenue_does_not_divide_by_zero(self):
        note = self.notes[0].model_copy(deep=True, update={"valor_servico": Decimal("0.00")})
        workbook = self.read_workbook(NFSeExporter.generate_excel([note]))
        sheet = workbook["Resumo Gerencial"]
        self.assertEqual(sheet["B5"].value, 0)
        self.assertEqual([sheet.cell(row, 3).value for row in range(5, 13)], [0] * 8)

    def test_annotations_resolve_without_missing_imports(self):
        for method in (NFSeExporter.generate_excel, NFSeExporter._build_sheet_resumo):
            self.assertIn("periodo_info", get_type_hints(method))

    def test_download_from_persisted_samples_returns_valid_xlsx(self):
        with TemporaryDirectory(prefix="nfse-xlsx-test-") as folder:
            storage = JSONStorage(Path(folder))
            for note in self.notes:
                storage.save_note(note)
            with patch("app.main.storage", storage), TestClient(app) as client:
                response = client.get("/api/export/excel")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"],
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.assertRegex(response.headers["content-disposition"],
                             r"attachment; filename=Relatorio_NFSe_Nacional_\d{8}_\d{6}\.xlsx")
            workbook = self.read_workbook(response.content)
            self.assertEqual(workbook["Notas Fiscais"].max_row, 5)
            self.assertEqual(workbook["Resumo Gerencial"]["B7"].value, 1907.21)

    def test_empty_database_keeps_clear_error_response(self):
        with patch("app.main.storage") as storage, TestClient(app) as client:
            storage.get_all_notes.return_value = []
            response = client.get("/api/export/excel")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Não há notas fiscais", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
