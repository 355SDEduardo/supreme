CREATE TABLE IF NOT EXISTS nfse.nfse_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id VARCHAR(100) NOT NULL,
    company_id VARCHAR(100) NOT NULL,
    chave_nfse VARCHAR(120) NOT NULL,
    numero_nfse VARCHAR(50),
    competencia VARCHAR(7) NOT NULL,
    data_emissao DATE,
    prestador_cnpj VARCHAR(18),
    tomador_documento VARCHAR(18),
    tomador_razao_social VARCHAR(255),
    valor_servico NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    valor_liquido NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    valor_total_retencoes NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    status_conciliacao VARCHAR(40) DEFAULT 'CONCILIADO',
    xml_storage_path TEXT,
    note_payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_nfse_tenant_chave UNIQUE (organization_id, company_id, chave_nfse)
);
CREATE INDEX IF NOT EXISTS idx_nfse_tenant_comp ON nfse.nfse_notes(organization_id, company_id, competencia);
CREATE INDEX IF NOT EXISTS idx_nfse_payload_gin ON nfse.nfse_notes USING GIN (note_payload);

-- ============================================================================
-- 13. SCHEMA: nfe (MS-07: Conferidor NF-e, ICMS-ST, DIFAL e Comparação ZIPs)
-- ============================================================================
CREATE TABLE IF NOT EXISTS nfe.fiscal_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id VARCHAR(100) NOT NULL,
    company_id VARCHAR(100) NOT NULL,
    ncm_code VARCHAR(20) NOT NULL,
    cest_code VARCHAR(20),
    description TEXT,
    st_status VARCHAR(50),
    mva_percentage NUMERIC(8, 4),
    rule_payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_nfe_catalog_ncm UNIQUE (organization_id, company_id, ncm_code)
);

CREATE TABLE IF NOT EXISTS nfe.processing_sessions (
    session_id VARCHAR(100) PRIMARY KEY,
    organization_id VARCHAR(100) NOT NULL,
    company_id VARCHAR(100) NOT NULL,
    summary_payload JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '2 hours'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 14. SCHEMA: tax_audit (MS-08: Auditoria Tributária Federal)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tax_audit.audit_snapshots (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id VARCHAR(100) NOT NULL,
    company_id VARCHAR(100) NOT NULL,
    periodo VARCHAR(20) NOT NULL DEFAULT 'default',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    snapshot_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tax_audit_active ON tax_audit.audit_snapshots(organization_id, company_id, is_active);

