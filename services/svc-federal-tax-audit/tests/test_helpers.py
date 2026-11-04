import unittest
from svc_federal_tax_audit.tools.audit_engine import parse_br_number, normalize_competencia, format_competencia_display, calculate_lc224_presumption, desagregar_csrf

class TestAuditEngineHelpers(unittest.TestCase):
    """Testes dos utilitários de parsing, cálculo e normalização temporal."""

    def test_parse_br_number(self):
        # Padrão brasileiro com vírgula e ponto
        self.assertEqual(parse_br_number("1.234,56"), 1234.56)
        self.assertEqual(parse_br_number("R$ 1.234,56"), 1234.56)
        self.assertEqual(parse_br_number(" 446.144,60 "), 446144.60)
        
        # Padrão internacional com ponto
        self.assertEqual(parse_br_number("1234.56"), 1234.56)
        self.assertEqual(parse_br_number("100.00"), 100.00)
        
        # Inteiros e tipos nativos
        self.assertEqual(parse_br_number(100), 100.0)
        self.assertEqual(parse_br_number(1234.56), 1234.56)
        
        # Entradas nulas e inválidas (sem exceptions e sem números inflacionados)
        self.assertEqual(parse_br_number(None), 0.0)
        self.assertEqual(parse_br_number("-"), 0.0)
        self.assertEqual(parse_br_number(""), 0.0)
        self.assertEqual(parse_br_number("INVÁLIDO"), 0.0)
        self.assertEqual(parse_br_number("null"), 0.0)

    def test_normalize_competencia(self):
        # MM/YYYY
        self.assertEqual(normalize_competencia("01/2026"), "2026-01")
        self.assertEqual(normalize_competencia("08-2026"), "2026-08")
        
        # YYYY/MM ou YYYY-MM
        self.assertEqual(normalize_competencia("2026/01"), "2026-01")
        self.assertEqual(normalize_competencia("2026-08"), "2026-08")
        
        # Datas completas ISO e BR
        self.assertEqual(normalize_competencia("2026-01-15T10:00:00"), "2026-01")
        self.assertEqual(normalize_competencia("15/01/2026"), "2026-01")

        # Exibição
        self.assertEqual(format_competencia_display("2026-01"), "01/2026")

    def test_calculate_lc224_presumption(self):
        # 1. Receita até R$ 1.250.000,00 -> 32%
        rec_abaixo = 1000000.0
        self.assertEqual(calculate_lc224_presumption(rec_abaixo, "IRPJ", 1), 320000.0)
        self.assertEqual(calculate_lc224_presumption(rec_abaixo, "CSLL", 2), 320000.0)

        # 2. Receita acima de R$ 1.250.000,00 no 1º Trimestre IRPJ
        # Receita real de T1: 1.326.345,74
        # Base esperada = 1.250.000 * 0.32 + 76.345,74 * 0.352 = 400.000 + 26.873,70 = 426.873,70
        base_t1_irpj = calculate_lc224_presumption(1326345.74, "IRPJ", 1)
        self.assertEqual(base_t1_irpj, 426873.70)

        # 3. CSLL no 1º Trimestre (regras da LC 224 iniciam no 2º trimestre) -> 32% linear
        # 1.326.345,74 * 0.32 = 424.430,64
        base_t1_csll = calculate_lc224_presumption(1326345.74, "CSLL", 1)
        self.assertEqual(base_t1_csll, 424430.64)

        # 4. Receita real de T2: 1.519.272,38
        # Base esperada = 1.250.000 * 0.32 + 269.272,38 * 0.352 = 400.000 + 94.783,88 = 494.783,88
        base_t2_irpj = calculate_lc224_presumption(1519272.38, "IRPJ", 2)
        base_t2_csll = calculate_lc224_presumption(1519272.38, "CSLL", 2)
        self.assertEqual(base_t2_irpj, 494783.88)
        self.assertEqual(base_t2_csll, 494783.88)

    def test_desagregar_csrf(self):
        # Nota 134: vretcsll = 596.13 (sobre 12.820,08 a 4,65%)
        # PIS (0.65%): 12.820,08 * 0.0065 = 83.33 -> 596.13 * (0.65/4.65) = 83.33
        # COFINS (3.00%): 12.820,08 * 0.03 = 384.60 -> 596.13 * (3.00/4.65) = 384.60
        # CSLL (1.00%): 12.820,08 * 0.01 = 128.20 -> 596.13 * (1.00/4.65) = 128.20
        res = desagregar_csrf(596.13)
        self.assertAlmostEqual(res["pis"], 83.33, places=2)
        self.assertAlmostEqual(res["cofins"], 384.60, places=2)
        self.assertAlmostEqual(res["csll"], 128.20, places=2)
        self.assertAlmostEqual(res["pis"] + res["cofins"] + res["csll"], 596.13, places=2)
