"""Todos os relatórios devem discriminar os seis tributos retidos."""

import csv
import io
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.exporter import NFSeExporter
from app.models import NFSNacionalModel, Participante, TributacaoFederal
from app.storage import JSONStorage

with patch("app.storage.JSONStorage"):
    from app.main import app


TAX_NAMES = ["ISSQN", "INSS", "PIS", "COFINS", "IRRF", "CSLL"]
HEADERS = [f"{name} Retido (R$)" for name in TAX_NAMES]
CSV_HEADERS = [f"Valor_Ret_{name}_R$" for name in ["ISS", *TAX_NAMES[1:]]]
EXPECTED = [Decimal(value) for value in ("5.00", "11.00", "1.65", "7.60", "1.50", "1.00")]


def make_note(retained=True):
    return NFSNacionalModel(
        chave_nfse="000001" if retained else "000002",
        numero_nfse=1 if retained else 2,
        data_competencia=date(2026, 1, 1),
        data_hora_processamento=datetime(2026, 1, 2),
        data_emissao_dps=datetime(2026, 1, 2),
        emitente=Participante(razao_social="Prestador de teste"),
        tomador=Participante(razao_social='Cliente São João; "Teste"'),
        valor_servico=Decimal("100.00"),
        valor_issqn=Decimal("5.00"),
        tipo_retencao_issqn=2 if retained else 1,
        valor_total_retencoes=Decimal("27.75") if retained else Decimal("0.00"),
        valor_liquido=Decimal("72.25") if retained else Decimal("100.00"),
        tributos_federais=TributacaoFederal(
            tp_retencao_pis_cofins=2 if retained else 0,
            valor_pis=Decimal("1.65"),
            valor_cofins=Decimal("7.60"),
            valor_ret_cp_inss=Decimal("11.00") if retained else Decimal("0.00"),
            valor_ret_irrf=Decimal("1.50") if retained else Decimal("0.00"),
            valor_ret_csll=Decimal("1.00") if retained else Decimal("0.00"),
        ),
    )


class RetentionExportTests(unittest.TestCase):
    def setUp(self):
        self.notes = [make_note(), make_note(False)]

    def test_all_excel_sheets_have_individual_tax_columns(self):
        workbook = load_workbook(io.BytesIO(NFSeExporter.generate_excel(self.notes)))
        self.addCleanup(workbook.close)
        for sheet in workbook:
            with self.subTest(sheet=sheet.title):
                header_row = next((row for row in sheet if all(name in [c.value for c in row] for name in HEADERS)), None)
                self.assertIsNotNone(header_row, f"Colunas de retenção ausentes em {sheet.title}")
                columns = {cell.value: cell.column for cell in header_row}
                indexes = [columns[name] for name in HEADERS]
                self.assertEqual(indexes, list(range(indexes[0], indexes[0] + 6)))
                row = header_row[0].row + 1
                self.assertEqual([Decimal(str(sheet.cell(row, column).value)) for column in indexes], EXPECTED)
                for column in indexes:
                    self.assertEqual(sheet.cell(row, column).number_format, NFSeExporter.FORMAT_CURRENCY)
                if sheet.title != "Resumo Gerencial":
                    self.assertEqual([sheet.cell(row + 1, column).value for column in indexes], [0] * 6)
                    self.assertNotIn("PIS/COFINS Retido (R$)", columns)
                    self.assertNotIn("Outras Retenções (R$)", columns)

    def test_csv_columns_values_and_existing_information(self):
        content = NFSeExporter.generate_csv(self.notes)
        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter=";")
        rows = list(reader)
        self.assertTrue(all(header in reader.fieldnames for header in CSV_HEADERS))
        self.assertEqual(len(reader.fieldnames), len(set(reader.fieldnames)))
        self.assertEqual(len(rows), 2)
        self.assertNotIn(None, rows[0])
        self.assertEqual([rows[0][header] for header in CSV_HEADERS], ["5,00", "11,00", "1,65", "7,60", "1,50", "1,00"])
        self.assertEqual([rows[1][header] for header in CSV_HEADERS], ["0,00"] * 6)
        self.assertEqual(rows[1]["Valor_PIS_R$"], "1,65")
        self.assertEqual(rows[1]["Valor_COFINS_R$"], "7,60")
        self.assertEqual(rows[0]["Total_Retencoes_R$"], "27,75")
        self.assertEqual(rows[0]["Chave_Acesso"], "000001")
        self.assertEqual(rows[0]["Tomador_Razao_Social"], 'Cliente São João; "Teste"')

    def test_excel_preserves_assessed_taxes_and_formats_when_not_withheld(self):
        workbook = load_workbook(io.BytesIO(NFSeExporter.generate_excel([self.notes[1]])))
        self.addCleanup(workbook.close)
        sheet = workbook["Notas Fiscais"]
        columns = {cell.value: cell.column for cell in sheet[1]}
        for header, expected in (("Valor ISSQN (R$)", 5), ("Valor PIS (R$)", 1.65),
                                 ("Valor COFINS (R$)", 7.60), ("Total Retenções (R$)", 0)):
            self.assertEqual(sheet.cell(2, columns[header]).value, expected)
        self.assertEqual(sheet.cell(2, columns["ISS Retido?"]).value, "Não (Prestador)")
        self.assertEqual(sheet.cell(2, columns["Chave de Acesso"]).value, "000002")

    def test_summary_keeps_declared_total_when_it_differs_from_taxes(self):
        self.notes[0].valor_total_retencoes = Decimal("30.00")
        workbook = load_workbook(io.BytesIO(NFSeExporter.generate_excel(self.notes, periodo_info="01/2026")))
        self.addCleanup(workbook.close)
        sheet = workbook["Resumo Gerencial"]
        row = next((row for row in sheet if row[0].value == HEADERS[0]), None)
        self.assertIsNotNone(row)
        values = {cell.value: sheet.cell(cell.row + 1, cell.column).value for cell in row if cell.value}
        self.assertEqual(values["Total declarado (R$)"], 30)
        self.assertEqual(values["Total identificado (R$)"], 27.75)
        self.assertEqual(values["Diferença (R$)"], 2.25)
        self.assertEqual(sheet["A5"].value, "Indicador Fiscal / Contábil")

    def test_export_endpoints_and_module_have_same_tax_values(self):
        with TemporaryDirectory(prefix="nfse-all-retencoes-") as folder:
            storage = JSONStorage(Path(folder))
            for note in self.notes:
                storage.save_note(note)
            with patch("app.main.storage", storage), TestClient(app) as client:
                responses = {fmt: client.get(f"/api/export/{fmt}") for fmt in ("excel", "csv", "json")}
                for fmt, response in responses.items():
                    self.assertEqual(response.status_code, 200, fmt)
                report = client.get("/api/retencoes?competencia=2026-01").json()
        data = responses["json"].json()
        self.assertEqual(data["metadata"]["total_notas"], 2)
        exported = next(note for note in data["notas"] if note["chave_nfse"] == "000001")
        keys = ["iss", "inss", "pis", "cofins", "irrf", "csll"]
        self.assertIn("retencoes", exported)
        self.assertEqual([Decimal(str(exported["retencoes"][key])) for key in keys], EXPECTED)
        self.assertEqual([Decimal(report["totais"][key]) for key in keys], EXPECTED)
        exempt = next(note for note in data["notas"] if note["chave_nfse"] == "000002")
        self.assertEqual(list(exempt["retencoes"].values()), [0] * 6)
        self.assertEqual(exempt["tributos_federais"]["valor_pis"], 1.65)


if __name__ == "__main__":
    unittest.main()
