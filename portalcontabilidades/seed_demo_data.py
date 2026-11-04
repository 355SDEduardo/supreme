"""Seed rich, realistic Brazilian accounting & BPO demo data into portal_contabil.db."""
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
import uuid

from portalcontabilidades.core.database import SessionLocal, Base, engine
from portalcontabilidades.features.multiempresa.models import (
    Organization, Company, User, UserCompanyRole, CompanyTeamAssignment
)
from portalcontabilidades.features.obrigacoes.models import (
    TaxObligation, CompanyObligation, Task, TaskAuditLog
)
from portalcontabilidades.features.financeiro.models import (
    PayableReceivableBill, BillApproval, BillingLog
)
from portalcontabilidades.features.conciliacao.models import (
    BankAccount, BankStatement, BankTransaction
)
from portalcontabilidades.features.documentos.models import (
    Document, DocumentReceipt, DocumentChecklist, DocumentChecklistItem
)
from portalcontabilidades.features.analytics.models import (
    FinancialSnapshot, ChartOfAccounts
)
from portalcontabilidades.features.automacao_ia.models import (
    AiExtraction, AiClassificationSuggestion, AiAnomalyAlert
)
from portalcontabilidades.features.integracoes_fiscais.models import (
    FiscalTransmission, FiscalReceipt
)
from portalcontabilidades.features.portal_cliente.models import (
    ClientTicket, TicketMessage, DocumentDownloadReceipt
)
from portalcontabilidades.features.seguranca.models import (
    DigitalCertificate, AuditLog, PrivacyConsent
)
from portalcontabilidades.features.seguranca.crypto_vault import (
    encrypt_payload, encrypt_string
)

def run_seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Check if already seeded
        if db.query(Organization).filter(Organization.id == "org-default-01").first():
            print("Database already has default organization. Cleaning and re-seeding for consistency...")
            db.query(AuditLog).delete()
            db.query(PrivacyConsent).delete()
            db.query(DigitalCertificate).delete()
            db.query(DocumentDownloadReceipt).delete()
            db.query(TicketMessage).delete()
            db.query(ClientTicket).delete()
            db.query(FiscalReceipt).delete()
            db.query(FiscalTransmission).delete()
            db.query(AiAnomalyAlert).delete()
            db.query(AiClassificationSuggestion).delete()
            db.query(AiExtraction).delete()
            db.query(FinancialSnapshot).delete()
            db.query(ChartOfAccounts).delete()
            db.query(DocumentChecklistItem).delete()
            db.query(DocumentChecklist).delete()
            db.query(DocumentReceipt).delete()
            db.query(Document).delete()
            db.query(BankTransaction).delete()
            db.query(BankStatement).delete()
            db.query(BankAccount).delete()
            db.query(BillingLog).delete()
            db.query(BillApproval).delete()
            db.query(PayableReceivableBill).delete()
            db.query(TaskAuditLog).delete()
            db.query(Task).delete()
            db.query(CompanyObligation).delete()
            db.query(TaxObligation).delete()
            db.query(CompanyTeamAssignment).delete()
            db.query(UserCompanyRole).delete()
            db.query(User).delete()
            db.query(Company).delete()
            db.query(Organization).delete()
            db.commit()

        print("Seeding organization and users...")
        org = Organization(
            id="org-default-01",
            name="Alpha Contabilidade & BPO Estratégico",
            tax_id="00000000000191"
        )
        db.add(org)

        admin = User(
            id="super-admin-01",
            organization_id="org-default-01",
            full_name="Lucas Rocha (Sócio Administrador)",
            email="lucas@alphacontabil.com.br",
            hashed_password="mock_hashed_secret",
            global_role="super_admin",
            is_active=True,
            is_mfa_enabled=True,
            mfa_secret="JBSWY3DPEHPK3PXP"
        )
        analyst1 = User(
            id="user-analyst-1",
            organization_id="org-default-01",
            full_name="Mariana Silva (Analista Fiscal)",
            email="mariana.silva@alphacontabil.com.br",
            hashed_password="mock_hashed_secret",
            global_role="analyst",
            is_active=True,
            is_mfa_enabled=False
        )
        analyst2 = User(
            id="user-analyst-2",
            organization_id="org-default-01",
            full_name="Carlos Eduardo (Analista BPO Financeiro)",
            email="carlos.eduardo@alphacontabil.com.br",
            hashed_password="mock_hashed_secret",
            global_role="bpo_operator",
            is_active=True,
            is_mfa_enabled=False
        )
        analyst3 = User(
            id="user-analyst-3",
            organization_id="org-default-01",
            full_name="Beatriz Lima (Supervisora Contábil)",
            email="beatriz.lima@alphacontabil.com.br",
            hashed_password="mock_hashed_secret",
            global_role="supervisor",
            is_active=True,
            is_mfa_enabled=True
        )
        client_user = User(
            id="user-client-01",
            organization_id="org-default-01",
            full_name="Eduardo Santos (Diretor Nexus)",
            email="eduardo@nexustec.com.br",
            hashed_password="mock_hashed_secret",
            global_role="client_user",
            is_active=True,
            is_mfa_enabled=False
        )
        db.add_all([admin, analyst1, analyst2, analyst3, client_user])
        db.commit()

        print("Seeding client companies...")
        companies_data = [
            Company(
                id="comp-01",
                organization_id="org-default-01",
                corporate_name="Nexus Tecnologia e Inovação Ltda",
                trade_name="Nexus Tech",
                tax_id="11222333000181",
                tax_regime="simples_nacional",
                state_tax_id="112.345.678.900",
                municipal_tax_id="99887766",
                cnae_code="6201-5/01",
                status="active"
            ),
            Company(
                id="comp-02",
                organization_id="org-default-01",
                corporate_name="Vanguarda Serviços Médicos e Hospitalares Ltda",
                trade_name="Clínica Vanguarda",
                tax_id="23456789000195",
                tax_regime="lucro_presumido",
                state_tax_id="ISENTO",
                municipal_tax_id="55443322",
                cnae_code="8630-5/02",
                status="active"
            ),
            Company(
                id="comp-03",
                organization_id="org-default-01",
                corporate_name="Orion Indústria Metalúrgica e Comércio S/A",
                trade_name="Orion Metais",
                tax_id="34567890000130",
                tax_regime="lucro_real",
                state_tax_id="223.445.556.778",
                municipal_tax_id="11223344",
                cnae_code="2599-3/99",
                status="active"
            ),
            Company(
                id="comp-04",
                organization_id="org-default-01",
                corporate_name="Bellini Café & Gastronomia Eireli",
                trade_name="Café Bellini",
                tax_id="45678901000175",
                tax_regime="simples_nacional",
                state_tax_id="998.887.776.655",
                municipal_tax_id="33445566",
                cnae_code="5611-2/03",
                status="active"
            ),
            Company(
                id="comp-05",
                organization_id="org-default-01",
                corporate_name="Zenith Consultoria Empresarial e BPO Ltda",
                trade_name="Zenith Partners",
                tax_id="56789012000100",
                tax_regime="lucro_presumido",
                state_tax_id="ISENTO",
                municipal_tax_id="77889900",
                cnae_code="7020-4/00",
                status="onboarding"
            ),
        ]
        db.add_all(companies_data)
        db.commit()

        # Assignments
        assignments = [
            CompanyTeamAssignment(company_id="comp-01", analyst_user_id="user-analyst-1", department="fiscal"),
            CompanyTeamAssignment(company_id="comp-01", analyst_user_id="user-analyst-2", department="bpo"),
            CompanyTeamAssignment(company_id="comp-02", analyst_user_id="user-analyst-1", department="fiscal"),
            CompanyTeamAssignment(company_id="comp-03", analyst_user_id="user-analyst-3", department="contabil"),
            CompanyTeamAssignment(company_id="comp-04", analyst_user_id="user-analyst-2", department="bpo"),
        ]
        db.add_all(assignments)
        db.commit()

        print("Seeding master tax obligations catalog...")
        obligations = [
            TaxObligation(
                id="ob-das",
                code="DAS",
                name="Documento de Arrecadação do Simples Nacional",
                sphere="federal",
                periodicity="mensal",
                due_day_rule="20_postpone",
                applicable_regimes=["simples_nacional"],
                has_receipt_required_default=True
            ),
            TaxObligation(
                id="ob-dctfweb",
                code="DCTFWEB",
                name="Declaração de Débitos e Créditos Tributários Federais",
                sphere="federal",
                periodicity="mensal",
                due_day_rule="15_anticipate",
                applicable_regimes=["simples_nacional", "lucro_presumido", "lucro_real"],
                has_receipt_required_default=True
            ),
            TaxObligation(
                id="ob-reinf",
                code="REINF",
                name="Escrituração Fiscal Digital de Retenções (EFD-Reinf)",
                sphere="federal",
                periodicity="mensal",
                due_day_rule="15_anticipate",
                applicable_regimes=["simples_nacional", "lucro_presumido", "lucro_real"],
                has_receipt_required_default=True
            ),
            TaxObligation(
                id="ob-esocial",
                code="ESOCIAL",
                name="Fechamento de Folha eSocial (S-1299)",
                sphere="trabalhista",
                periodicity="mensal",
                due_day_rule="15_anticipate",
                applicable_regimes=["simples_nacional", "lucro_presumido", "lucro_real"],
                has_receipt_required_default=True
            ),
            TaxObligation(
                id="ob-fgts",
                code="FGTS_DIGITAL",
                name="Guia do FGTS Digital",
                sphere="trabalhista",
                periodicity="mensal",
                due_day_rule="20_anticipate",
                applicable_regimes=["simples_nacional", "lucro_presumido", "lucro_real"],
                has_receipt_required_default=True
            ),
            TaxObligation(
                id="ob-iss",
                code="ISS_MENSAL",
                name="Apuração e Emissão de Guia de ISS Municipal",
                sphere="municipal",
                periodicity="mensal",
                due_day_rule="10_postpone",
                applicable_regimes=["lucro_presumido", "lucro_real"],
                has_receipt_required_default=True
            ),
        ]
        db.add_all(obligations)
        db.commit()

        print("Seeding tasks for competence 2026-09 and 2026-10...")
        today = date(2026, 10, 9)
        sample_tasks = [
            Task(
                id="task-01",
                company_id="comp-01",
                obligation_code="DAS",
                competence="2026-09",
                title="Apuração e Emissão de Guia DAS - Nexus Tech",
                statutory_due_date=date(2026, 10, 20),
                internal_deadline=date(2026, 10, 16),
                status="completed",
                assigned_to="user-analyst-1",
                reviewed_by="super-admin-01",
                has_receipt_required=True,
                receipt_file_id="rec-das-01",
                receipt_file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            ),
            Task(
                id="task-02",
                company_id="comp-01",
                obligation_code="DCTFWEB",
                competence="2026-09",
                title="Transmissão DCTFWeb Previdenciária - Nexus Tech",
                statutory_due_date=date(2026, 10, 15),
                internal_deadline=date(2026, 10, 13),
                status="in_progress",
                assigned_to="user-analyst-1",
                has_receipt_required=True
            ),
            Task(
                id="task-03",
                company_id="comp-01",
                obligation_code="ESOCIAL",
                competence="2026-09",
                title="Fechamento de Folha de Pagamento eSocial - Nexus Tech",
                statutory_due_date=date(2026, 10, 15),
                internal_deadline=date(2026, 10, 11),
                status="in_review",
                assigned_to="user-analyst-3",
                has_receipt_required=True
            ),
            Task(
                id="task-04",
                company_id="comp-02",
                obligation_code="REINF",
                competence="2026-09",
                title="Transmissão EFD-Reinf Série R-4000 - Clínica Vanguarda",
                statutory_due_date=date(2026, 10, 15),
                internal_deadline=date(2026, 10, 10),
                status="todo",
                assigned_to="user-analyst-1",
                has_receipt_required=True
            ),
            Task(
                id="task-05",
                company_id="comp-03",
                obligation_code="DCTFWEB",
                competence="2026-09",
                title="Consolidação DCTFWeb e Fechamento Retenções - Orion Metais",
                statutory_due_date=date(2026, 10, 15),
                internal_deadline=date(2026, 10, 13),
                status="in_progress",
                assigned_to="user-analyst-3",
                has_receipt_required=True
            ),
            Task(
                id="task-06",
                company_id="comp-04",
                obligation_code="FGTS_DIGITAL",
                competence="2026-09",
                title="Geração da Guia FGTS Digital - Café Bellini",
                statutory_due_date=date(2026, 10, 20),
                internal_deadline=date(2026, 10, 18),
                status="todo",
                assigned_to="user-analyst-1",
                has_receipt_required=True
            ),
            Task(
                id="task-07",
                company_id="comp-02",
                obligation_code="ISS_MENSAL",
                competence="2026-09",
                title="Declaração e Guia ISS Sociedade Uniprofissional - Vanguarda",
                statutory_due_date=date(2026, 10, 10),
                internal_deadline=date(2026, 10, 8),
                status="overdue",
                assigned_to="user-analyst-1",
                has_receipt_required=True
            ),
        ]
        db.add_all(sample_tasks)
        db.commit()

        print("Seeding bank accounts & OFX statements for conciliation...")
        b1 = BankAccount(
            id="bank-acc-01",
            company_id="comp-01",
            bank_code="341",
            bank_name="Banco Itaú S/A",
            agency_number="0456",
            account_number="28491-0",
            current_balance=Decimal("148520.45"),
            is_active=True
        )
        b2 = BankAccount(
            id="bank-acc-02",
            company_id="comp-01",
            bank_code="077",
            bank_name="Banco Inter S/A",
            agency_number="0001",
            account_number="9981244-1",
            current_balance=Decimal("35240.10"),
            is_active=True
        )
        b3 = BankAccount(
            id="bank-acc-03",
            company_id="comp-02",
            bank_code="237",
            bank_name="Banco Bradesco S/A",
            agency_number="1245",
            account_number="78120-3",
            current_balance=Decimal("210400.00"),
            is_active=True
        )
        db.add_all([b1, b2, b3])
        db.commit()

        stmt1 = BankStatement(
            id="stmt-01",
            bank_account_id="bank-acc-01",
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 9),
            opening_balance=Decimal("120000.00"),
            closing_balance=Decimal("148520.45"),
            total_credits=Decimal("45000.00"),
            total_debits=Decimal("16479.55"),
            status="partially_reconciled"
        )
        db.add(stmt1)
        db.commit()

        trxs = [
            BankTransaction(
                id="trx-01",
                bank_account_id="bank-acc-01",
                statement_id="stmt-01",
                fitid="ITAU-20261001-998811",
                transaction_date=date(2026, 10, 2),
                amount=Decimal("25000.00"),
                memo="PIX RECEBIDO - CLIENTE ACME CORP SOLUCOES",
                status="pending"
            ),
            BankTransaction(
                id="trx-02",
                bank_account_id="bank-acc-01",
                statement_id="stmt-01",
                fitid="ITAU-20261003-998812",
                transaction_date=date(2026, 10, 3),
                amount=Decimal("-4500.00"),
                memo="TED PAGAMENTO FORNECEDOR - DELL COMPUTADORES BRASIL",
                status="pending"
            ),
            BankTransaction(
                id="trx-03",
                bank_account_id="bank-acc-01",
                statement_id="stmt-01",
                fitid="ITAU-20261005-998813",
                transaction_date=date(2026, 10, 5),
                amount=Decimal("-68.50"),
                memo="TAR CONTA CORRENTE PACOTE EMPRESARIAL",
                status="pending"
            ),
            BankTransaction(
                id="trx-04",
                bank_account_id="bank-acc-01",
                statement_id="stmt-01",
                fitid="ITAU-20261006-998814",
                transaction_date=date(2026, 10, 6),
                amount=Decimal("12500.00"),
                memo="TED TRANSF TITULARIDADE INTERPJ -> ITAU",
                status="pending"
            ),
            BankTransaction(
                id="trx-05",
                bank_account_id="bank-acc-01",
                statement_id="stmt-01",
                fitid="ITAU-20261008-998815",
                transaction_date=date(2026, 10, 8),
                amount=Decimal("-3200.00"),
                memo="PAGAMENTO BOLETO ALUGUEL EDIFICIO FARIA LIMA",
                status="pending"
            ),
        ]
        db.add_all(trxs)
        db.commit()

        print("Seeding Payable & Receivable bills (Contas a Pagar e Receber)...")
        bills = [
            # Contas a Pagar
            PayableReceivableBill(
                id="bill-pay-01",
                company_id="comp-01",
                type="payable",
                counterparty_name="Edifício Empresarial Faria Lima Ltda",
                counterparty_tax_id="11222333000181",
                document_number="ALUG-102026",
                original_amount=Decimal("3200.00"),
                final_amount=Decimal("3200.00"),
                issue_date=date(2026, 10, 1),
                due_date=date(2026, 10, 10),
                payment_method="boleto",
                barcode_line="3419179001010435100479102015000219800000320000",
                status="pending_approval",
                required_approvals=1,
                current_approvals=0
            ),
            PayableReceivableBill(
                id="bill-pay-02",
                company_id="comp-01",
                type="payable",
                counterparty_name="Amazon Web Services Brasil Ltda",
                counterparty_tax_id="23456789000195",
                document_number="INV-BR-89218",
                original_amount=Decimal("1850.30"),
                final_amount=Decimal("1850.30"),
                issue_date=date(2026, 10, 2),
                due_date=date(2026, 10, 15),
                payment_method="pix",
                pix_key="financeiro@aws.amazon.com",
                status="pending_approval",
                required_approvals=1,
                current_approvals=0
            ),
            PayableReceivableBill(
                id="bill-pay-03",
                company_id="comp-01",
                type="payable",
                counterparty_name="Google Cloud Brasil Internet Ltda",
                counterparty_tax_id="34567890000130",
                document_number="NF-9921",
                original_amount=Decimal("940.00"),
                final_amount=Decimal("940.00"),
                issue_date=date(2026, 10, 1),
                due_date=date(2026, 10, 20),
                payment_method="boleto",
                barcode_line="2379338128600830135285600006330779800000094000",
                status="approved",
                required_approvals=1,
                current_approvals=1
            ),
            # Contas a Receber (Aging List)
            PayableReceivableBill(
                id="bill-rec-01",
                company_id="comp-01",
                type="receivable",
                counterparty_name="Acme Corporation Brasil Ltda",
                counterparty_tax_id="45678901000175",
                document_number="FAT-2026-101",
                original_amount=Decimal("25000.00"),
                final_amount=Decimal("25000.00"),
                issue_date=date(2026, 9, 20),
                due_date=date(2026, 10, 20),
                payment_method="boleto",
                status="draft" # No prazo
            ),
            PayableReceivableBill(
                id="bill-rec-02",
                company_id="comp-01",
                type="receivable",
                counterparty_name="Logística Global Express S/A",
                counterparty_tax_id="56789012000100",
                document_number="FAT-2026-089",
                original_amount=Decimal("14200.00"),
                final_amount=Decimal("14200.00"),
                issue_date=date(2026, 8, 15),
                due_date=date(2026, 9, 15), # 24 dias atrasado (1-30 dias)
                payment_method="boleto",
                status="draft"
            ),
            PayableReceivableBill(
                id="bill-rec-03",
                company_id="comp-01",
                type="receivable",
                counterparty_name="Varejo Supermercados Delta Ltda",
                counterparty_tax_id="11222333000181",
                document_number="FAT-2026-054",
                original_amount=Decimal("8750.00"),
                final_amount=Decimal("8750.00"),
                issue_date=date(2026, 7, 10),
                due_date=date(2026, 8, 10), # 60 dias atrasado (31-60 dias)
                payment_method="boleto",
                status="draft"
            ),
        ]
        db.add_all(bills)
        db.commit()

        print("Seeding DRE and Cash Flow analytical snapshots...")
        snapshots = [
            # Accrual DRE for comp-01 in 2026-09
            FinancialSnapshot(
                company_id="comp-01",
                competence="2026-09",
                view_type="accrual_dre",
                line_code="1.01",
                line_description="Receita Bruta de Serviços",
                realized_amount=Decimal("245000.00")
            ),
            FinancialSnapshot(
                company_id="comp-01",
                competence="2026-09",
                view_type="accrual_dre",
                line_code="1.02",
                line_description="Deduções da Receita (ISS, PIS, COFINS)",
                realized_amount=Decimal("24500.00")
            ),
            FinancialSnapshot(
                company_id="comp-01",
                competence="2026-09",
                view_type="accrual_dre",
                line_code="2.01",
                line_description="Custos dos Serviços Prestados (CSP/Equipe Técnica)",
                realized_amount=Decimal("98000.00")
            ),
            FinancialSnapshot(
                company_id="comp-01",
                competence="2026-09",
                view_type="accrual_dre",
                line_code="3.01",
                line_description="Despesas Operacionais e Administrativas",
                realized_amount=Decimal("42000.00")
            ),
            FinancialSnapshot(
                company_id="comp-01",
                competence="2026-09",
                view_type="accrual_dre",
                line_code="4.01",
                line_description="Receitas Financeiras (Rendimentos CDB/DI)",
                realized_amount=Decimal("3200.00")
            ),
            FinancialSnapshot(
                company_id="comp-01",
                competence="2026-09",
                view_type="accrual_dre",
                line_code="4.02",
                line_description="Despesas Financeiras e Tarifas Bancárias",
                realized_amount=Decimal("1100.00")
            ),
        ]
        db.add_all(snapshots)
        db.commit()

        print("Seeding Documents & Compliance Checklists...")
        doc1 = Document(
            id="doc-das-01",
            company_id="comp-01",
            competence="2026-09",
            department="fiscal",
            file_name="Guia_DAS_Simples_Nacional_2026-09.pdf",
            storage_path="./storage/uploads/comp-01/2026-09/Guia_DAS.pdf",
            mime_type="application/pdf",
            file_size_bytes=142050,
            file_hash_sha256="9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            version=1,
            is_latest=True,
            status="validated",
            ocr_status="processed"
        )
        doc2 = Document(
            id="doc-ofx-01",
            company_id="comp-01",
            competence="2026-09",
            department="contabil",
            file_name="Extrato_Bancario_Itau_Setembro_2026.ofx",
            storage_path="./storage/uploads/comp-01/2026-09/Extrato_Itau.ofx",
            mime_type="application/x-ofx",
            file_size_bytes=48520,
            file_hash_sha256="5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
            version=1,
            is_latest=True,
            status="validated",
            ocr_status="not_applicable"
        )
        db.add_all([doc1, doc2])
        db.commit()

        rec1 = DocumentReceipt(
            id="rec-das-01",
            document_id="doc-das-01",
            receipt_code="PROT-2026-10-ALPHA-009182",
            file_name="Guia_DAS_Simples_Nacional_2026-09.pdf",
            file_hash_sha256="9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            file_size_bytes=142050,
            uploaded_by="user-analyst-1",
            ip_address="189.40.12.88",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
        )
        db.add(rec1)
        db.commit()

        chk1 = DocumentChecklist(
            id="chk-01",
            company_id="comp-01",
            competence="2026-09",
            title="Fechamento Mensal de Documentos - Competência 2026-09",
            completion_percentage=75.0
        )
        db.add(chk1)
        db.commit()

        chk_items = [
            DocumentChecklistItem(
                checklist_id="chk-01",
                title="Extratos Bancários Mensais em formato OFX",
                department="contabil",
                is_required=True,
                is_fulfilled=True,
                fulfilled_by_document_id="doc-ofx-01"
            ),
            DocumentChecklistItem(
                checklist_id="chk-01",
                title="Notas Fiscais de Entrada (XMLs fornecedores)",
                department="fiscal",
                is_required=True,
                is_fulfilled=True
            ),
            DocumentChecklistItem(
                checklist_id="chk-01",
                title="Comprovantes de Pagamento de Guias e Salários",
                department="bpo",
                is_required=True,
                is_fulfilled=True
            ),
            DocumentChecklistItem(
                checklist_id="chk-01",
                title="Relatório de Faturamento Mensal (Cartões de Crédito / Maquininhas)",
                department="fiscal",
                is_required=True,
                is_fulfilled=False
            ),
        ]
        db.add_all(chk_items)
        db.commit()

        print("Seeding AI & Automation records (Sugestões, OCR, Anomalias)...")
        ai_sugg1 = AiClassificationSuggestion(
            id="sugg-01",
            company_id="comp-01",
            transaction_id="trx-02",
            suggested_debit_account="1.1.03.01 - Equipamentos de Informática (Ativo Imobilizado)",
            suggested_credit_account="1.1.01.02 - Banco Itaú Conta Movimento",
            suggested_cost_center="CC-02 - Tecnologia e Infraestrutura",
            suggested_narrative="Aquisição de hardware e computadores portáteis p/ equipe de desenvolvimento conf NF Dell",
            confidence_score=Decimal("96.80"),
            decision_status="pending_review"
        )
        ai_sugg2 = AiClassificationSuggestion(
            id="sugg-02",
            company_id="comp-01",
            transaction_id="trx-05",
            suggested_debit_account="3.1.02.04 - Aluguéis e Condomínios (Despesas Administrativas)",
            suggested_credit_account="1.1.01.02 - Banco Itaú Conta Movimento",
            suggested_cost_center="CC-01 - Sede Administrativa SP",
            suggested_narrative="Pagamento de locação comercial sala 1402 Faria Lima",
            confidence_score=Decimal("99.20"),
            decision_status="accepted",
            reviewed_by="user-analyst-2",
            reviewed_at=datetime.now(timezone.utc)
        )
        db.add_all([ai_sugg1, ai_sugg2])
        db.commit()

        anom1 = AiAnomalyAlert(
            id="anom-01",
            company_id="comp-01",
            anomaly_type="abnormal_expense_spike",
            severity="warning",
            details={
                "description": "Despesa com serviços em nuvem (AWS) aumentou 48% em relação à média dos últimos 3 meses.",
                "current_amount": 1850.30,
                "historical_average": 1250.00,
                "deviation_pct": 48.0
            },
            dismissed=False
        )
        anom2 = AiAnomalyAlert(
            id="anom-02",
            company_id="comp-01",
            anomaly_type="duplicate_payment_risk",
            severity="critical",
            details={
                "description": "Boleto com valor idêntico (R$ 3.200,00) e mesmo cedente detectado em duplicidade com NF anterior.",
                "counterparty": "Edifício Faria Lima Ltda",
                "risk_amount": 3200.00
            },
            dismissed=False
        )
        db.add_all([anom1, anom2])
        db.commit()

        print("Seeding Fiscal Transmissions & CND records...")
        fisc1 = FiscalTransmission(
            id="fisc-01",
            company_id="comp-01",
            system_target="esocial",
            event_type="S-1200",
            competence="2026-09",
            environment="production",
            idempotency_key="ESOCIAL-S1200-COMP01-202609-01",
            xml_sent_payload="<eSocial><evtRemun id='S1200'>...</evtRemun></eSocial>",
            xml_response_payload="<retornoEvento><codigo>201</codigo><descricao>Sucesso</descricao></retornoEvento>",
            receipt_number="1.2.202609.000000000000491823",
            status="accepted",
            attempts=1,
            last_attempt_at=datetime.now(timezone.utc)
        )
        fisc2 = FiscalTransmission(
            id="fisc-02",
            company_id="comp-01",
            system_target="efd_reinf",
            event_type="R-4020",
            competence="2026-09",
            environment="production",
            idempotency_key="REINF-R4020-COMP01-202609-01",
            xml_sent_payload="<Reinf><evtRetPJ id='R4020'>...</evtRetPJ></Reinf>",
            status="queued",
            attempts=0
        )
        db.add_all([fisc1, fisc2])
        db.commit()

        print("Seeding Client Portal Tickets & Messages...")
        tick1 = ClientTicket(
            id="tick-01",
            company_id="comp-01",
            category="admission",
            title="Admissão de Desenvolvedor Senior - Início 15/10/2026",
            status="in_analysis",
            priority="high",
            sla_hours=24,
            sla_due_at=datetime.now(timezone.utc) + timedelta(hours=18),
            assigned_agent_id="user-analyst-3",
            created_by_user_id="user-client-01",
            structured_data={
                "employee_name": "Guilherme de Almeida",
                "cpf": "123.456.789-00",
                "role": "Engenheiro de Software Senior",
                "salary": 14500.00,
                "start_date": "2026-10-15"
            }
        )
        tick2 = ClientTicket(
            id="tick-02",
            company_id="comp-01",
            category="fiscal",
            title="Dúvida sobre Retenção de ISS em Nota Fiscal de Exportação de Software",
            status="resolved",
            priority="medium",
            sla_hours=48,
            sla_due_at=datetime.now(timezone.utc) - timedelta(hours=5),
            assigned_agent_id="user-analyst-1",
            created_by_user_id="user-client-01",
            structured_data={"service_code": "01.01", "destination_country": "Estados Unidos"}
        )
        db.add_all([tick1, tick2])
        db.commit()

        msg1 = TicketMessage(
            id="msg-01",
            ticket_id="tick-01",
            sender_id="user-client-01",
            sender_type="client_user",
            message_body="Olá time Alpha, segue solicitação de admissão do Guilherme com início previsto para próxima segunda-feira.",
            channel="portal"
        )
        msg2 = TicketMessage(
            id="msg-02",
            ticket_id="tick-01",
            sender_id="user-analyst-3",
            sender_type="staff_agent",
            message_body="Recebido Eduardo! Já validamos os dados cadastrais no eSocial e estamos gerando o contrato de trabalho e exame admissional.",
            channel="portal"
        )
        db.add_all([msg1, msg2])
        db.commit()

        print("Seeding Digital Certificates & Vault...")
        fake_cert_bytes = b"MOCK_ENCRYPTED_PFX_CERTIFICATE_ICP_BRASIL_A1_ALPHA_TEST"
        enc_payload = encrypt_payload(fake_cert_bytes)
        enc_pwd = encrypt_string("CertSenhaForte2026!")

        cert1 = DigitalCertificate(
            id="cert-01",
            company_id="comp-01",
            certificate_type="a1_file",
            encrypted_certificate_payload=enc_payload,
            encrypted_password=enc_pwd,
            issued_to_tax_id="11222333000181",
            common_name="NEXUS TECNOLOGIA E INOVACAO LTDA:11222333000181",
            valid_from=datetime(2025, 11, 1, 0, 0, 0, tzinfo=timezone.utc),
            valid_until=datetime(2026, 10, 21, 23, 59, 59, tzinfo=timezone.utc), # Expira em 12 dias (Alerta 15d!)
            status="active"
        )
        cert2 = DigitalCertificate(
            id="cert-02",
            company_id="comp-02",
            certificate_type="a1_file",
            encrypted_certificate_payload=enc_payload,
            encrypted_password=enc_pwd,
            issued_to_tax_id="23456789000195",
            common_name="CLINICA VANGUARDA SERVICOS MEDICOS LTDA:23456789000195",
            valid_from=datetime(2026, 5, 15, 0, 0, 0, tzinfo=timezone.utc),
            valid_until=datetime(2027, 5, 15, 23, 59, 59, tzinfo=timezone.utc), # 218 dias (Status Verde)
            status="active"
        )
        db.add_all([cert1, cert2])
        db.commit()

        print("Seeding Audit Trail logs & LGPD...")
        logs = [
            AuditLog(
                actor_user_id="super-admin-01",
                organization_id="org-default-01",
                company_id="comp-01",
                action="session_login_mfa_verified",
                resource_type="authentication",
                resource_id="user-super-admin-01",
                ip_address="189.40.12.88",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                payload_snapshot={"auth_method": "totp_mfa", "status": "success"}
            ),
            AuditLog(
                actor_user_id="user-analyst-1",
                organization_id="org-default-01",
                company_id="comp-01",
                action="tax_guide_uploaded",
                resource_type="document",
                resource_id="doc-das-01",
                ip_address="189.40.12.88",
                payload_snapshot={"obligation": "DAS", "competence": "2026-09", "amount": 14205.80}
            ),
            AuditLog(
                actor_user_id="user-analyst-2",
                organization_id="org-default-01",
                company_id="comp-01",
                action="ai_classification_approved",
                resource_type="ai_suggestion",
                resource_id="sugg-02",
                ip_address="189.40.12.88",
                payload_snapshot={"decision": "accepted", "confidence": 99.2}
            ),
        ]
        db.add_all(logs)
        db.commit()

        consent = PrivacyConsent(
            user_id="super-admin-01",
            term_version="2026.1",
            legal_basis="Execucao de Contrato e Cumprimento de Obrigacao Legal (LGPD Art. 7)",
            ip_address="189.40.12.88",
            user_agent="Mozilla/5.0"
        )
        db.add(consent)
        db.commit()

        print("Demo seed completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run_seed()
